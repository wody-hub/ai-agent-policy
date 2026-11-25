# Paseo agent lifecycle (draft 0.1.0)

상태: 초안(2026-11-25). [Orca Worker lifecycle rulebook](orca-worker-lifecycle.md)에 대응하는 Paseo용 규칙이다. 승인 전에는 Orca 문서를 대체하지 않는다. 공통 원칙은 [paseo-common](../policy/paseo-common.md)을 따른다.

근거 표기: [DOC]/[SRC]/[GH]는 `.local-artifacts/paseo-migration/evidence/paseo-technical-research.md`(Paseo v0.17.4, 소스 commit 8b2e14f, 2026-11-24)의 표기를 따른다. [MCP]는 2026-11-25 이 세션에서 읽은 Paseo MCP 도구 스키마다. [미확인]은 실행으로 검증하지 않은 항목이다.

이 규칙은 Paseo가 관리하는 에이전트에만 적용한다. 프로젝트 Task 등록, Gitflow·작업 위치, Human Gate, 사용자 승인 규칙은 기존 정책을 그대로 따른다. Claude Code 내부 서브에이전트(Agent 도구)나 직접 연 터미널 세션은 Paseo 관리 에이전트가 아니며 자동 정리되지 않는다.

## 1. 상태와 용어

| Paseo 상태 | 의미 [DOC lifecycle] | 정책상 해석 |
|---|---|---|
| `initializing` | 런타임 준비 중 | 시작 전. 업무 시작으로 보고하지 않는다 |
| `running` | 턴 실행 중 | 실행 중. 정리·교체·같은 범위 재배정 금지 |
| `idle` | 턴 종료, 런타임 유지(1시간 유휴 후 런타임 해제, 다음 프롬프트에 재개) | 턴 정산 후보. 결과 확인 전에는 미정산 |
| `error` | 턴 오류 | 실패 후보. 원인 분류(모델/비모델) 후 처리 |
| `closed` | 영속 기록만 있고 런타임 없음(재개 가능) | 데몬 재시작 후 흔함. 자동 재개되지 않는다 |
| archived | soft delete(`archivedAt`) | 정리 완료 |

- **Owner**: Worker를 만든 부모 에이전트. 소유 기록은 Paseo가 붙이는 `paseo.parent-agent-id` 라벨이다 [DOC]. `list_agents`에는 라벨 필터가 없으므로 [MCP] Owner는 자신이 만든 자식 ID 목록(작업 원장)을 Task 로컬 기록에 따로 둔다.
- **배정(Dispatch 대응)**: Worker 하나에 보낸 하나의 업무 프롬프트와 그 턴. 원장에 `agentId`, 배정 시각, 목적, 기대 결과, 시도 번호를 남긴다.
- **정산(settlement)**: 배정한 턴이 끝났고(`idle`/`error`/`closed`), 그 턴의 결과 보고와 검증 근거를 Owner가 확보했으며, 이 사실을 원장에 기록한 상태.
- **정리(release 대응)**: 정산 후 `archive_agent`.

## 2. Worker 생성 (worker-start 대응)

1. 생성 전 확인: Task ID와 승인 범위, 대상 워크스페이스 ID와 작업 위치 검사(4절), 라우팅 결정(프로필·이유), 동시 실행 한도(전체 Worker 3, 프리미엄 1)의 현재 사용량, 같은 Task·범위의 활성 Worker 부재.
2. `create_agent` 호출 [MCP]:
   - `provider`: 프로필의 `provider/model`.
   - `settings.modeId`, `settings.thinkingOptionId`: 프로필 값. 프로필에 없는 상향(`bypassPermissions`, `full-access`)은 하지 않는다.
   - `workspaceId`: 검사를 통과한 worktree 워크스페이스. 생략하면 Owner 자신의 워크스페이스에 생기므로 반드시 지정한다.
   - `title`: 실제 전체 Git 브랜치명(60자 제한. 넘으면 앞부분을 보존하고 원장에 원래 이름을 기록).
   - `labels`: `task.id=<TASK_ID>`, `role=<worker|reviewer|lookup>`, `route=<프로필 id>`, `attempt=<n>`. 라벨 키 규칙은 초안이며 Paseo 측 예약 키와 충돌하지 않는지 [미확인].
   - `notifyOnFinish`: 기본 true 유지.
   - `initialPrompt`: 아래 배정 계약.
3. 배정 계약(초기 프롬프트에 포함): 역할과 재위임 금지, 정책 버전, Task ID, 워크스페이스 ID·경로·기준 ref/SHA, 담당 파일·책임, 인터페이스, 제약, 완료 조건, 금지 행위(push·merge·배포·삭제·전역 설정 수정), 장시간 프로세스·로그 규칙, 보고 형식(7절), Owner ID.
4. 시작 확인: 생성 응답은 수락일 뿐이다. `get_agent_status`가 `running`이거나 활동 기록에 첫 턴이 보일 때 "시작"으로 기록한다. 응답이 모호하면 새 Worker를 추가하지 않고 같은 `agentId`의 상태를 먼저 확인한다.
5. 요청한 provider·model·thinking과 상태 스냅샷에서 확인한 값을 따로 기록한다. 스냅샷에 실제 model·thinking이 나오는지는 [미확인]이며, 확인할 수 없으면 "실행 모델 미검증"으로 남긴다.

## 3. 대기와 완료 수신 (scoped wait 대응)

- 기본은 push 방식이다. `create_agent`/`send_agent_prompt`의 `notifyOnFinish`로 finish·error·permission 알림이 Owner에게 프롬프트로 들어온다 [DOC/SRC]. Owner는 배정 후 턴을 끝내고 기다린다. MCP에는 대기 도구가 없다 [DOC].
- 반복 폴링 금지. 알림이 와야 할 시점이 지났는데 오지 않으면 해당 `agentId` 하나만 `get_agent_status`로 한 번 확인하고 다시 턴을 끝낸다. 장시간 작업은 만료(`expiresIn` 또는 `maxRuns`)를 둔 `create_heartbeat`를 보조 신호로 쓴다. 만료 없는 heartbeat는 만들지 않는다.
- 알림을 받으려면 Owner에게 런타임이 있어야 한다. 미처리 구독이 있는 유휴 Owner는 유휴 정리에서 보호된다고 문서화돼 있으나 [DOC], 관련 버그(#8464)가 있으므로 Owner가 `closed`가 된 뒤 알림이 실제로 전달되는지는 [미확인]이다.
- 알림은 at-least-once이고 턴 식별 정보가 없다 [DOC]. Owner는 원장의 (agentId, 배정 번호)로 중복을 걸러 같은 결과로 두 번 후속 조치하지 않는다.
- 타임아웃이나 알림 부재는 완료도 실패도 아니다.

## 4. 작업 위치 준비

### 4.1 워크스페이스 생성 (Orca worktree create 대응)

1. 생성 전: 저장소 실제 루트, WORK_TYPE(feature/release/hotfix), 기준 브랜치(통합 또는 운영), 기준 ref(로컬/원격 구분과 선택 이유), `git rev-parse <ref>`로 확정한 SHA, 예정 Gitflow 브랜치명, Paseo 프로젝트 ID를 기록한다. Task 정책이 있으면 Task ID·문서 정본 위치도 확인한다.
2. `create_workspace` [MCP]: `isolation: worktree`, `mode: branch-off`, `baseBranch: <기준 ref>`, `branchName: <Gitflow 브랜치명>`, `projectId: <확인한 프로젝트>`, `path: <해당 저장소 기준 체크아웃>`. `baseBranch`를 생략해 현재 워크스페이스 브랜치에서 분기하게 두지 않는다.
3. 생성 후: worktree realpath, `git rev-parse --show-toplevel`, 현재 브랜치명, 초기 `HEAD` == 1단계 SHA, 워크스페이스 ID, 프로젝트 ID를 확인·기록한다. 하나라도 다르면 Worker를 배정하지 않고 보고한다. 브랜치를 rename하거나 reset으로 맞추지 않는다.
4. `baseBranch`가 원격 ref(`origin/dev`)를 받는지, 로컬 브랜치와 다를 때 어느 쪽을 쓰는지는 [미확인]이다. 첫 사용 시 3단계 HEAD 비교로 판정하고 결과를 기록한다.
5. 진행 중에 기준 브랜치가 이동한 것은 거부 사유가 아니다. 초기 HEAD 일치만 요구한다.
6. 여러 저장소에 걸친 업무는 저장소별 워크스페이스로 나누고 하나의 Task ID로 연결하며 저장소별 기준 SHA를 기록한다.
7. Orca의 "기준 워크스페이스 자식(parent)" 개념은 Paseo에 없다. Paseo 워크스페이스는 프로젝트 소속만 가진다. 따라서 "Git base와 부모는 별개 사실" 원칙은 Paseo에서 (a) Git 기준 ref·SHA, (b) Paseo 프로젝트 ID, (c) Worker의 부모 에이전트 라벨을 각각 확인하는 규칙이 된다. Orca의 `--no-parent` 금지 규칙은 대상이 없어 폐기하고, 그 목적(기능 브랜치에서 재분기 금지)은 `baseBranch` 명시와 HEAD 확인으로 유지한다.

### 4.2 정책 설치 준비 (worktree readiness 대응)

Orca 규칙의 개념을 그대로 이월한다.

1. 로컬 정책 설치가 필요한 프로젝트는 worktree 생성과 별도로 정책 설치 단계를 거친 뒤 일반 Worker를 배정한다. Git worktree 생성이 무시(ignored) 파일을 복사했다고 가정하지 않는다.
2. 프로젝트의 검토된 버전별 manifest(진입 지침, 정책 snapshot·manifest, guard, 클라이언트별 hook 설정)에 따라 지원 설치 도구로 설치하거나, 프로젝트가 허용하면 담당 AI가 검증된 원본에서 명시된 파일만 덮어쓰지 않고 복사한다. 복사 후 bytes·권한을 원본·manifest와 대조하고 원본 버전·해시·대상·결과를 기록한다. 비밀·개인 Task context·무관한 설정은 복사하지 않는다.
3. worktree 생성 / 파일 설치 / 클라이언트 신뢰 / hook 실제 로딩을 서로 다른 상태로 기록한다. `paseo.json` setup 훅 성공이나 워크스페이스 생성 성공만으로 준비 완료로 보지 않는다.
4. 파일이 없으면 "정책 설치 필요", 설치 bytes·hook 로딩을 확인할 수 없으면 구체적 차단 사유를 기록하고 일반 배정을 멈춘다. Task·worktree·변경을 보존하고 승인된 설치·복구 경로를 같은 worktree에 적용한다. worktree를 다시 만들거나 클라이언트를 바꾸거나 같은 생성을 반복해 검사를 피하지 않는다.
5. 일반 업무 재개 전 새 세션에서 선택한 클라이언트의 정책·hook 로딩과 허용/거부 사례를 확인한다. Paseo Claude 에이전트는 Claude Agent SDK로 로컬 `claude`를 실행하고 user·project·local 설정을 읽는다고 되어 있으나 [SRC], 프로젝트 hook이 Paseo 경유 세션에서 실제로 실행되는지는 [미확인]이므로 첫 사용 시 확인한다.
6. 프로젝트의 설치 전용 Task만 제한된 설치 예외로 진행할 수 있다.

## 5. 정산과 정리 (settlement / worker-release 대응)

1. 완료 알림을 받으면 Worker의 결과 보고(7절)와 검증 근거를 Task 로컬 기록에 보존한다. Claude Worker는 Owner에게 보낸 보고 메시지, Codex Worker는 완료 알림에 포함된 마지막 응답 또는 `get_agent_activity`로 확인한다.
2. `get_agent_status`로 상태가 `running`이 아님을 확인하고, 대기 중 권한 요청이 없는지 본다. 쓰기 Worker는 worktree의 `git status`로 미커밋 변경을 결과 보고와 대조한다.
3. 원장에 정산을 기록한 직후 `archive_agent`로 정리하고 `archived` / `archive_pending` / `archive_unknown` 중 하나를 기록한다. 정산된 실패도 결과 확보 후 정리한다.
4. 정리하지 않는 대상: `running`·`initializing`, 정산 불명, 사용자 소유(사용자가 직접 만들었거나 탭에서 쓰는 중), 이 Task 이전부터 있던 에이전트, 소유가 확인되지 않은 에이전트.
5. 사용자가 그 세션을 남겨 달라고 명시한 경우에만 열어 두고 이유와 보유자를 기록한다.
6. `archive_agent`는 실행 중이면 턴을 중단한다 [MCP]. 따라서 정산 전 호출은 결과 유실 위험이 있다. 부모를 archive하면 같은 워크스페이스의 자식도 함께 archive된다 [DOC]. Owner는 미정산 자식이 있는 동안 자신을 archive하지 않는다.
7. `kill_agent`(영구 종료)는 정상 정리 수단이 아니다. 멈춘 에이전트에만 쓰고, 사용자 소유가 아니며 Owner가 직접 만든 경우로 한정해 이유를 기록한다. `cancel_agent`는 턴만 중단하고 에이전트는 남긴다.
8. `archive_workspace`는 Paseo가 만든 worktree를 마지막 참조 이후 제거한다 [DOC]. worktree 삭제와 같으므로 Task 승인 범위에 명시됐거나 사용자가 승인한 경우에만 쓰고, 실행 전 미커밋·미푸시 변경이 없음을 확인한다.
9. 런타임 증거가 없는 세션 종료·정리를 주장하지 않는다. 확인할 수 없으면 "lifecycle 미확인"으로 보고한다.

## 6. 중복 방지와 교체

- 배정 전에 원장과 `list_agents`(필요하면 `statuses`, `cwd` 필터)로 같은 Task·범위의 활성 Worker가 없는지 확인한다. 이미 있으면 새로 만들지 않고 기존 Worker에 `send_agent_prompt`로 이어서 보낸다.
- 교체 조건: 기존 쓰기 Worker가 `running`이 아님이 확인되고, 잔여 쓰기 변경이 결과 보고와 대조되었으며, 기존 Worker가 정산·정리(또는 정리 보류 사유 기록)된 뒤에만 같은 범위의 새 쓰기 Worker를 만든다. 타임아웃·알림 부재만으로 교체하지 않는다. 사용자가 수동으로 멈춘 경우에도 같은 기준을 적용한다.
- 모델 계열을 바꿀 때는 기존 worktree와 변경을 보존하고 목표, diff, 테스트 결과, 시도·가설·남은 문제를 인계한다. 시도 횟수는 이어서 센다.
- `send_agent_prompt`의 `interrupt`·`steer`는 실행 중 턴을 끊거나 끼어든다. 아직 읽지 않은 steer는 턴이 끝나면 유실될 수 있다 [MCP]. 정정·중단이 꼭 필요할 때만 쓰고 기본은 `queue`다.

## 7. Worker 결과 형식 (Worker result 대응)

각 Worker는 하나의 간결한 보고를 보낸다: Task ID, Worker agentId, 결과(완료/차단/승인 필요/실패), 변경 파일과 요약, 실행한 검증 명령·결과·근거 위치, 미확인 항목·차단 사유, 다음 조치, 직접 띄운 백그라운드 프로세스와 로그 크기. Claude Worker는 Paseo 도구가 있으면 `send_agent_prompt`로 Owner에게 `PROJECT_DONE:`/`BLOCKED:`/`NEED_APPROVAL:` 접두사 보고를 한 번 보낸다(진행 중 보고에는 접두사를 쓰지 않는다). Codex Worker는 같은 내용을 최종 응답으로 남긴다.

Owner는 원장에 요청·확인된 provider/model/thinking, 경과 시간, 시도 번호와 실패 종류, 검증 상태, 정리 상태를 함께 기록한다. 가능하면 `ai_policy.usage record`로 같은 Task ID에 기록한다. Paseo `usage` 명령은 계정 한도를 보여 줄 뿐 에이전트별 소비량이 아니다 [DOC]. 에이전트별 토큰은 SDK `lastUsage`로만 확인 가능하며 MCP 경로는 [미확인]이므로 없으면 비워 둔다.

## 8. Owner 장애와 인계 (Controller resume / consumer_fenced 대응)

Paseo에는 Run 바인딩·`run-use`·`consumer_fenced`가 없다. 소유는 부모 라벨로 고정되고, 완료 알림은 부모에게만 간다. 부모 재지정(`detach`)은 CLI·SDK 수동 기능이며 MCP 도구가 아니다 [DOC].

1. Owner가 `closed`면 같은 Owner에게 프롬프트를 보내 재개한다(런타임은 다음 프롬프트에 재개된다 [DOC]). 새 Owner를 만들어 우회하지 않는다.
2. Owner를 재개할 수 없으면 Root(또는 사용자)가 새 Owner를 지정하고, 새 Owner는 먼저 기존 원장과 각 자식의 `get_agent_status`/`get_agent_activity`를 읽어 정산·미정산·불확실을 분류한다. 불확실한 배정은 다시 실행하지 않는다. 기존 자식의 완료 알림은 여전히 옛 Owner로 가므로, 새 Owner는 그 자식들에 대해 알림 없이 개별 상태 확인으로 정산한다. 새 작업은 새 Owner가 만든 자식에게만 준다.
3. 계획된 인계에서는 현재 Owner가 새 배정을 멈추고 정산 완료·미정산 목록·불확실 요청을 원장에 남긴 뒤 넘긴다.
4. Owner는 하나다. 같은 자식에게 두 에이전트가 업무 프롬프트를 보내는 상태를 만들지 않는다.

## 9. 데몬 재시작·장애 대응

- 데몬 재시작 후 에이전트는 `closed`로 돌아오며 `agents.resumeOnStartup` 기본값이 꺼져 있어 자동 재개되지 않는다 [SRC config.ts:842]. 완료 구독은 복원된다고 문서화돼 있다 [DOC].
- 데몬이 수락 직후 약 2초 안에 죽으면 수락된 메시지가 유실될 수 있다(#8436) [GH]. 재시작을 인지하면 Owner는 원장의 모든 미정산 Worker 상태를 확인하고, 마지막 배정이 실제로 시작됐는지(활동 기록) 대조한다. 시작 근거가 없으면 같은 Worker에 같은 배정을 한 번 다시 보낸다. 이것은 비모델 재시도로 센다(원인별 최대 3회).
- 데스크톱 앱이 데몬을 관리하면 앱 종료 시 데몬도 멈춘다(`keepRunningAfterQuit: false`) [SRC]. 장시간 작업 전 데몬 실행 방식을 확인한다.
- 장시간 세션·다수 에이전트에서 메모리 증가 이슈가 있다(#6522, #6477, #4450) [GH]. 끝난 에이전트를 즉시 정리하는 규칙이 이 위험도 줄인다.

## 10. 실행 환경 점검 (세션 시작 시 1회, 값은 기록하지 않음)

- 데몬이 깨끗한 로그인 셸에서 시작됐는지: Claude Code 세션 안에서 띄운 데몬은 자식 `claude`가 "Not logged in"으로 실패할 수 있다(#3618) [GH].
- 데몬 환경 변수(`ANTHROPIC_BASE_URL`, API 키, 프록시)가 자식 에이전트로 전달된다 [SRC]. 존재 여부만 확인하고 값은 출력하지 않는다. 전역 정책의 기존 프록시 설정을 유지할지 여부는 사용자 결정이다.
- 한국어: macOS 데스크톱 앱이 관리하는 데몬은 locale이 `C`라 터미널에서 한글이 깨질 수 있다(#3513) [GH]. UTF-8 locale(`LANG`/`LC_ALL`)을 가진 셸에서 `paseo daemon start`로 띄우는 우회가 제안돼 있으나 [미확인]. 한글 경로·커밋 메시지·Kanban 파일을 다루는 작업 전에 확인한다.
- relay 꺼짐, loopback listen, 비밀번호 설정 여부, Paseo 도구 주입 설정을 확인한다. 바꾸는 것은 사용자 승인 사항이다.
