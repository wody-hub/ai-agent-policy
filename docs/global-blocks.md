# 전역 지침 블록 분리와 적용 도구

Claude Code `~/.claude/CLAUDE.md`와 Codex `~/.codex/AGENTS.md`의 전역 지침을 **독립 블록(core, orca, paseo; 기본 설치는 core + paseo)**으로 나누어 생성하고, 계획·적용·복원이 가능한 도구(`ai_policy/globalblocks.py`)로 안전하게 반영한다. 도구는 독립 실행형이며 `ai_policy.__main__`·bundle 코드에 연결되어 있지 않다.

## 구조

| 블록 | 마커 | 버전 | 성격 | 기본 설치 |
| --- | --- | --- | --- | --- |
| core | `ai-agent-policy:core-claude` / `ai-agent-policy:core-codex` | 1.5.0 | 호스트 중립 모델 라우팅(호스트별 `core.claude.md`, `core.codex.md`) | 예 |
| orca | `ai-agent-policy:orca-policy` | 1.4.0 (동결) | Orca 방식, 병행기·보관 (두 호스트 공통 `orca.md`) | 아니오 (`--with-orca`) |
| paseo | `ai-agent-policy:paseo-policy` | 0.1.1-draft | Paseo 방식, 짧은 게이트·역할·Human Gate (두 호스트 공통 `paseo.md`) | 예 |

**기본 설치는 core + paseo**다(`blocks.json`의 `hosts.<host>.default_blocks`). 항상 로드되는 텍스트(토큰 비용)를 줄이기 위해 Orca 블록은 저장소 원본으로만 두고 기본으로 반영하지 않는다. 진행 중인 Orca Run은 프로젝트 수준 Orca 정책과 `docs/orca-worker-lifecycle.md`를 따른다. 필요하면 `--with-orca`로 core, orca, paseo 세 블록을 모두 관리한다.

각 블록은 `<!-- MARKER:start version=V -->` … `<!-- MARKER:end -->` 로 감싸고 core, (orca,) paseo 순서로 한 줄씩 띄워 이어 붙인다. core 마커가 호스트별이므로 claude 파일에 codex 블록을 잘못 적용하면 `host_mismatch`로 거부한다. 블록별로 따로 버전을 올리고, 코어는 환경별 정책이 해당 환경에서만 적용된다는 "Orchestration environments" 문단 하나만 가진다.

기존(legacy) 블록 `ai-agent-policy:claude` / `ai-agent-policy:codex`(1.4.0)는 코어 지침과 Paseo 안내 문단이 섞여 있었다. 이를 선택한 블록 묶음으로 대체한다.

### 크기

렌더링된 블록의 바이트 크기(마커 줄 포함)와 legacy 블록 대비 증감이다. 블록 사이 빈 줄 1바이트를 포함한다.

| 호스트 | core | paseo | orca | legacy | 기본(core+paseo) | 기본 증감 | `--with-orca` | `--with-orca` 증감 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| claude | 7508 | 1396 | 3115 | 7217 | 8905 | +1688 | 12021 | +4804 |
| codex | 7628 | 1396 | 3115 | 7337 | 9025 | +1688 | 12141 | +4804 |

`tests/test_global_blocks.py`가 기본 묶음의 증감이 2000바이트를 넘지 않는지 검사한다.

## 원본과 렌더링

원본은 `policy/global/`에 있다: `core.claude.md`, `core.codex.md`, `orca.md`, `paseo.md`, 그리고 버전·마커·원본 파일·호스트별 기본 블록·알려진 sha256을 담은 `blocks.json`. 렌더링은 결정적이다: 마커 시작 줄 + 본문(끝의 줄바꿈 제거) + 마커 끝 줄, 블록 사이는 빈 줄 하나, 마지막 끝 마커 뒤에 빈 줄은 없다. 같은 원본은 항상 같은 바이트를 만든다.

### 알려진 해시와 릴리스

`blocks.json`의 `known_sha256`은 legacy 블록(호스트별)과, 새 블록마다 호스트별로 릴리스된 블록 텍스트(시작 마커 줄부터 끝 마커 줄까지)의 sha256 목록이다. 원본 텍스트를 바꾸면 `python3 -B -m ai_policy.globalblocks hashes --host <host>`로 해시를 출력해 릴리스한 해시를 추가해야 하며, 현재 렌더의 해시가 목록에 없으면 테스트가 실패한다.

대상 파일의 새 블록은 다음과 같이 판정한다: 현재 렌더와 같으면 그대로, 목록에 있는 이전 릴리스이면 제자리 갱신, 목록에 없으면(손으로 고쳤거나 이전 릴리스인데 해시가 없으면) `unrecognized_block`, 블록의 `version`이 이 도구의 버전보다 새로우면 `downgrade_block`으로 거부한다. 두 거부는 내용을 확인한 뒤에만 `--overwrite-unrecognized`로 넘긴다.

## 사용법

저장소 루트에서 실행한다. 관리 마커 밖의 내용(개인 지침)은 읽기만 하며 출력에 찍지 않는다.

```bash
python3 -B -m ai_policy.globalblocks render --host claude        # 기본 블록(core, paseo) 출력, --with-orca로 orca 포함
python3 -B -m ai_policy.globalblocks check  --host claude --target ~/.claude/CLAUDE.md
python3 -B -m ai_policy.globalblocks sync   --host claude --target ~/.claude/CLAUDE.md        # 드라이런(기본)
python3 -B -m ai_policy.globalblocks sync   --host claude --target ~/.claude/CLAUDE.md --plan-sha256 <드라이런이 출력한 해시>
python3 -B -m ai_policy.globalblocks restore --target ~/.claude/CLAUDE.md --backup <백업 경로>   # 드라이런
python3 -B -m ai_policy.globalblocks restore --target ~/.claude/CLAUDE.md --backup <백업 경로> --plan-sha256 <해시>
```

- `check`: 읽기 전용. 상태는 `legacy`(알려진 1.4.0 블록 하나) / `current`(선택한 블록이 모두 존재, 블록별 `status`·`up_to_date`) / `partial` / `none` / `unrecognized`(손으로 고친 legacy). 종료 코드 0 = 이미 최신, 1 = 변경 필요, 2 = 오류.
- `sync`: 기본은 드라이런이다. 파일과 상태 디렉터리를 만들거나 쓰지 않고, 변경 전후 sha256(영역·전체 파일), 블록별 동작, 줄 수 diff 요약과 `plan_sha256`을 JSON으로 출력한다. 같은 명령에 `--plan-sha256`을 붙여야 적용한다. 해시는 대상 파일 바이트, 선택한 블록 묶음, 렌더 결과, 플래그에 묶여 있어 그 사이 파일이 바뀌거나 플래그가 다르면 거부한다.
- 적용 직전 대상 sha256을 다시 확인해(바뀌었으면 `target_changed`로 중단, 쓰기 없음, 임시 파일 없음) 같은 디렉터리의 임시 파일 → fsync → 원본 권한 복원 → `os.replace` 순으로 교체하고, 교체 후 다시 읽어 영역이 기대값이고 영역 밖이 원본과 같은지 확인한다. 실패하면 `applied: true`, `backup`과 함께 오류를 보고하고 종료 코드 2를 반환한다.
- 이미 최신이면 적용해도 아무것도 쓰지 않는다(바이트·mtime 유지, 백업 없음).
- 종료 코드: 0 = 정상·변경 없음·드라이런, 1 = 사람의 판단이 필요한 거부(`unrecognized_block`, `no_managed_block`, `partial_install`), 2 = 그 밖의 오류.

## 영역 판정과 거부

대상 파일에서 (a) 해당 호스트의 legacy 블록이 정확히 하나이고 새 블록이 없으면 그 자리를 선택한 블록 묶음으로 교체하고, (b) 선택한 새 블록이 각각 한 번씩 순서대로 있으면 각 블록을 제자리에서 갱신한다. 영역 밖은 바이트 그대로이며 쓰기 전에 도구가 이를 단언한다. 그 외는 쓰지 않고 거부한다: 관리 블록 없음(`no_managed_block`, 자동 삽입 없음), 새 블록과 legacy 혼재·선택한 블록 일부만 설치(`partial_install`), 선택하지 않은 이 도구의 블록이 있음(`unexpected_block`: `--with-orca`를 주거나 restore로 되돌린다), 다른 호스트의 core 마커(`host_mismatch`), 중복·중첩·짝이 안 맞는·순서가 바뀐·형식이 잘못된 마커, 다른 블록의 마커를 품은 블록, CRLF·UTF-8이 아닌 파일, 심볼릭 링크·하드링크·일반 파일이 아닌 대상, 8 MiB 초과.

블록 묶음을 바꾸는 일은 지원하지 않는다: `--with-orca`로 설치한 파일에 기본 묶음으로 sync하면 `unexpected_block`, 기본으로 설치한 파일에 `--with-orca`로 sync하면 `partial_install`로 거부한다. restore로 이전 백업으로 돌아간 뒤 원하는 묶음으로 다시 sync한다.

legacy 블록의 sha256이 `blocks.json`의 `known_sha256`에 없으면(손으로 고쳤으면) `unrecognized_block`으로 거부하며, 내용을 확인한 뒤에만 `--overwrite-unrecognized`로 덮어쓴다. 알려진 legacy 해시: claude `00b5a84d…`, codex `af42a251…`(각 1.4.0 블록, 시작 마커 줄부터 끝 마커 줄까지). 끝 마커가 파일의 마지막 줄이고 줄바꿈이 없으면 줄바꿈을 붙여 해시를 계산하며, 적용하면 파일 끝에 줄바꿈이 생긴다.

## 마이그레이션

1. `check`로 현재 상태가 `legacy`인지 본다.
2. `sync`를 드라이런으로 실행해 `state`, `selected_blocks`, `blocks`, `diff` 요약과 `plan_sha256`을 검토한다.
3. 같은 명령에 `--plan-sha256`을 붙여 적용한다. 적용 결과의 `backup`을 기록해 둔다.
4. `check`가 종료 코드 0과 `state: current`를 내는지 확인한다.

새 세션부터 바뀐 지침 파일을 읽고, 실행 중인 세션은 이전 텍스트를 유지한다.

## 롤백과 백업

적용 전에 대상 파일 전체를 복사해 둔다. 기본 위치는 `${XDG_STATE_HOME:-~/.local/state}/ai-policy/global-blocks/<sha256(대상 절대경로)[:8]>/backups/<파일명>.<UTC시각>.<sha8>`이다(상대 경로 `XDG_STATE_HOME`은 무시, `--state-dir`로 변경 가능). 디렉터리는 0700, 백업 파일은 0600이며, 심볼릭 링크이거나 다른 사용자 소유인 상태 디렉터리는 거부한다. 백업에는 개인 지침이 그대로 들어 있으므로 저장소나 공유 문서에 두지 않고 내용을 출력하지 않는다.

각 백업 옆에 사이드카 `<백업>.target`(0600, 대상 절대경로)을 만든다. `restore`는 백업 디렉터리 바로 아래의 일반 파일이면서 이름·sha8 규칙에 맞고 사이드카가 같은 대상을 가리키는 백업만 받는다(사이드카가 없으면 `backup_target_missing`, 다르면 `backup_target_mismatch`). 복원 전에 현재 대상도 같은 디렉터리에 먼저 저장(`pre_restore_backup`)하고, 같은 sha 재확인과 원자적 교체를 사용한다.

## 하지 않는 일

- 세션 시작 훅이나 자동 실행을 만들지 않는다. 사람이 드라이런과 해시를 확인해 실행한다.
- 설치 어댑터·bundle 매니페스트와 연결하지 않는다(`policy/bundle.json`, `policy/paseo-bundle.json`은 소유자가 따로 재생성한다).
- 실행 중인 세션의 지침을 바꾸지 않는다.
- 관리 마커가 없는 파일에는 블록을 자동으로 삽입하지 않는다.
- 파일 잠금은 사용하지 않는다. 마지막 sha256 재확인과 `os.replace` 사이에 아주 짧은 경쟁 구간이 남아 있어, 그 사이에 다른 프로그램이 같은 파일을 고치면 그 변경이 백업에만 남을 수 있다(백업은 교체 직전 원본이다).
- 하드링크된 대상(링크 수 > 1)은 쓰기·복원을 `target_hardlinked`로 거부한다(교체가 다른 링크를 떼어 놓기 때문). 읽기 전용 `check`는 허용한다.

## Orca 방식과 Paseo 방식 분리의 강제

`tests/test_global_blocks.py`가 다음을 검사한다: 기본 묶음에는 orca 블록이 없다. `orca.md`에는 "paseo"(대소문자 무관)가, `paseo.md`에는 "orca"가 없다. 코어 본문에서 "Orca"·"Paseo"는 단 하나의 "Orchestration environments" 문단 안에만 나오며 코어에는 "병행기" 문구가 없다. 두 소스 모두 마커 토큰을 포함하지 않는다. legacy 블록의 모든 문장이 core 또는 paseo에 남아 있다는 점(문장 단위 검사), `known_sha256`이 모든 블록·호스트의 현재 렌더를 포함한다는 점, 그리고 `known_sha256`이 보관된 legacy 블록(`tests/fixtures/global-blocks/`)과 일치한다는 점도 테스트로 고정한다.
