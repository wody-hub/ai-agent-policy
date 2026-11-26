# Paseo 프로젝트 공통 전략 설치 지시서

버전: `paseo-project-policy@v0.1.0-draft` · 기준일: 2026-11-25 · 모델 라우팅: 1.7.0

상태: 초안. 사용자 검토·승인 전에는 프로젝트에 설치하는 정본으로 쓰지 않는다. 이 문서는 [Orca 프로젝트 공통 전략 설치 지시서](orca-project-setup.md)(병행기 보관)를 Paseo 기준으로 옮긴 것이며, 같은 Task·Gitflow·검증 규칙을 Paseo의 에이전트·워크스페이스 모델에 맞춘다. Orca 전용 단계(`run-create`, Dispatch release, `consumer_fenced`·`run-use`, Orca parent workspace, `--no-parent`, `orca orchestration` 명령)는 대상이 없어 넣지 않았다.

Codex와 Claude Code 어느 쪽에서도 사용할 수 있는 프로젝트별 설치 지시서입니다. 기존 전역 지침을 유지하면서, Gitflow 기준의 Paseo 작업 워크스페이스와 도구 구분 없는 모델 배정 전략을 설치합니다. 공통 정책 본문은 [`policy/paseo-common.md`](policy/paseo-common.md), 상세 절차는 [Paseo agent lifecycle](docs/paseo-agent-lifecycle.md), 모델 매핑은 [Paseo 모델 라우팅](docs/paseo-model-routing.md)입니다.

## 사용 방법

1. 대상 프로젝트의 저장소에서 Paseo의 Claude 에이전트(권장: 프로필 `root-orchestrator`)를 엽니다. Paseo 도구가 없는 Codex 에이전트는 오케스트레이터가 될 수 없습니다.
2. 이 파일을 첨부하거나 로컬 경로로 읽게 한 뒤 다음과 같이 요청합니다.

   > 이 지시서를 끝까지 읽고 Paseo 프로젝트 전략을 설치해줘. 기존 전역 지침은 유지하고, 변경 전 백업과 실제 지원 기능 확인부터 진행해줘.

3. 여러 저장소를 묶는 프로젝트에서는 문서 저장소와 작업 대상 저장소를 지정합니다.
4. 설치 보고에서 파일 생성·Git 비추적, 새 워크스페이스 재설치·지침 로딩, 실행 차단 검증 상태를 각각 확인합니다.

이 문서는 실행 스크립트가 아닙니다. 아래 지시를 에이전트가 수행하면서 대상 환경에 맞는 문서·연결·지원되는 실행 검사를 설치합니다. 비즈니스 기능 구현, 운영 배포, 전역 정책 변경, Paseo 데몬·프로필·플러그인 설정 변경은 설치 범위에 포함하지 않습니다.

## 설치 프롬프트

아래 코드 블록 전체를 복사해 사용할 수도 있습니다.

```text
너는 기존 프로젝트의 Paseo AI 개발 환경 설치 담당자다. 다음 정책을 프로젝트별로 설치하고 검증해줘. 기존 Codex·Claude 전역 지침은 수정하지 않는다. 프로젝트의 소스 구조·아키텍처·라이브러리·API·DB를 임의로 변경하지 않는다. Paseo 데몬 설정·프로필·플러그인·schedule은 변경하지 않는다.

VERSION
paseo-project-policy@v0.1.0-draft (실행 계약) · 모델 라우팅 1.7.0

VARIABLES
- PROJECT_ROOT: 현재 프로젝트. 여러 저장소를 묶는 상위 폴더일 수 있다.
- GUIDE_DIR: 단일 저장소에서는 docs. 여러 저장소라면 확인한 팀 공유 문서 저장소 안의 경로.
- POLICY_DIR: GUIDE_DIR/paseo.
- INTEGRATION_BRANCH: 기존 dev 또는 develop 중 실제 프로젝트 통합 브랜치. dev를 develop으로 자동 rename하지 않는다.
- PRODUCTION_BRANCH: 기존 main 또는 master 중 실제 운영 브랜치. 이름만으로 추측하지 않고 프로젝트 Gitflow 매핑을 확인한다.
- WORK_TYPE: feature / release / hotfix. 일반 기능·수정·문서 작업은 feature, 운영 긴급 수정만 hotfix다.
- BRANCH_PATTERN: 기존 Gitflow 관례대로 feature/<업무명>, release/<버전>, hotfix/<버전>. suffix의 세부 표기는 프로젝트 관례를 보존하고 Task 연결표에서 TASK_ID와 연결한다.
- BASE_BRANCH: feature와 release는 INTEGRATION_BRANCH, hotfix는 PRODUCTION_BRANCH. 정책 설치·복구는 INTEGRATION_BRANCH에서 진행한다. 다른 역할의 브랜치로 자동 대체하지 않는다.
- BASE_REF: 선택한 BASE_BRANCH의 로컬 또는 확인한 원격 ref. 원격 이름과 선택 이유를 기록한다.
- BASE_REF 표기: 확인한 기준 ref에 한해 refs/heads/<branch> ↔ <branch>, refs/remotes/<remote>/<branch> ↔ <remote>/<branch>를 정규화한다. 로컬·원격 ref는 같은 SHA라도 합치지 않는다.
- WORKER_LIMIT: 운영상 동시 Worker 3개 이하, 프리미엄·최후 수단 모델 Worker 1개 이하. Paseo에는 이 상한을 강제하는 기능이 없으므로 Root가 `list_agents`와 원장으로 센다.
- OWNER_LEDGER: Task 로컬 기록 폴더(LOCAL_ARTIFACT_ROOT/<TASK_ID>/)의 Owner 원장. 개인 절대 경로·에이전트 ID·워크스페이스 ID는 여기에만 두고 팀 공유 문서에 넣지 않는다.

POLICY — 설치 산출물의 Git 비추적 계약
- Paseo 및 project-task-policy 설치·갱신으로 생성한 설정·지침·검사기·템플릿·snapshot·설치 기록은 로컬 설치 산출물이다. Git add·commit·push 대상에 포함하지 않고, 기준 브랜치에 설치 파일을 병합하는 것을 완료 조건으로 삼지 않는다.
- 대상은 설치가 생성한 AGENTS.md·AGENTS.override.md·CLAUDE.md, 도구별 프로젝트 로컬 설정·hook, .ai-agent-policy/의 snapshot·SHA256SUMS, scripts/ai-policy/의 설치 guard·adapter·검사 파일, POLICY_DIR의 생성 정책·INSTALLATION.md, 생성 Task 템플릿·GENERATED.md·로컬 실행 기록·백업이다. 실제 생성 경로를 설치 manifest에 열거하고 그 목록만 제외한다. docs/ 또는 scripts/ 전체를 ignore하지 않는다.
- 이 정책 저장소의 수작업 원본 설치 지시서와 실제 업무의 코드·설계·납품 문서·공유 Task README는 설치 산출물과 구분한다. 설치 산출물에 대한 커밋 금지가 업무 문서의 기존 커밋 계약을 없애지 않는다.
- 쓰기 전 각 대상 저장소에서 생성 경로의 기존 추적 여부를 git ls-files로 확인한다. 미추적 생성 경로는 해당 저장소의 git rev-parse --git-path info/exclude로 찾은 로컬 exclude에 등록하고 기존 패턴을 보존한다. 팀 .gitignore를 사용하는 경우에도 실제 설치 경로만 제외한다. ignore 설정은 이미 추적된 파일에 적용되지 않는다.
- 기존 추적 파일이 순수 설치 산출물인 경우, 추적 해제 대상과 로컬 백업을 확정한 마이그레이션에서만 git rm --cached -- <정확한 경로>로 index에서 제거하고 로컬 파일은 보존한다. 삭제·wildcard 일괄 untrack·git add -f·이력 재작성은 하지 않는다. 설치 과정에서 기존 커밋을 자동으로 되돌리지 않는다.
- 사람이 관리하는 추적 지침·설정과 설치 블록이 섞인 파일은 파일 전체를 자동 untrack하거나 삭제하지 않는다. 설치 내용을 도구가 지원하는 미추적 로컬 진입·설정으로 분리하고 기존 공유 파일을 보존한다. 지원되는 분리·로딩 방법이 없으면 그 설치 경로를 미지원으로 보고한다.
- 완료 전 manifest의 모든 설치 파일에 대해 git ls-files 결과가 비어 있고 git check-ignore -v --no-index로 제외 규칙이 확인되는지 검사한다. staging diff에 설치 파일이나 설치 블록이 섞이지 않았는지도 확인한다. 기존 추적 해제 대기인 파일은 비추적 완료로 보고하지 않는다.
- 미추적 설치 파일은 clone·새 worktree로 상속되지 않는다. 검증한 원본 버전·해시와 로컬 보정 manifest를 기준으로 새 워크스페이스에 다시 설치·로딩·guard 검증한다. 설치 파일을 커밋하거나 정책 누락 검사를 우회해 전파하지 않는다. 설치 source provenance는 원본 지시서 commit/버전과 실제 bytes/hash로 기록하며 설치 파일 자체의 commit SHA를 요구하지 않는다.
- 프로젝트는 신규 워크스페이스 생성 직후 일반 Worker 배정 전에 정책 설치 단계를 실행하도록 생성 절차를 구성한다. 검토된 버전별 manifest에 진입 지침, 정책 snapshot·manifest, guard, 사용하는 클라이언트별 hook 설정을 명시한다. 대상 실행 호스트에서 지원 설치 도구를 사용하거나 프로젝트가 허용하면 담당 AI가 검증된 원본에서 명시된 파일만 직접 복사한다. 복사 전 대상 존재 여부를 확인하고 복사 후 원본·manifest와 bytes·권한을 대조한다. 원본 버전·해시·대상·결과를 기록하고 기존 파일이나 사용자 변경이 예상과 다르면 덮어쓰지 않는다. 개인 Task context·비밀·무관한 설정은 복사하지 않는다. 파일 설치와 실제 세션 신뢰·hook 로딩·허용/거부 검사는 각각 확인한다. 지원 설치 도구나 허용된 직접 복사 경로가 없으면 설치 대기로 표시하고 승인된 복구 경로를 수행한다.

PHASE 0 — 발견·백업·설치 범위
1. 기존 AGENTS.md, AGENTS.override.md, CLAUDE.md, 프로젝트 rules, paseo.json, GENERATED.md와 관련 개발 문서를 먼저 확인한다. 기존 Orca·orca-setup 산출물이 있으면 삭제하지 않고 재사용 가능한 부분과 프로젝트 보정 섹션을 보존한다. 병행기 동안 기존 Orca가 소유한 진행 중 Run·worktree는 Orca 규칙으로 마무리하고 Paseo로 옮기지 않는다.
2. 각 Git 저장소의 실제 루트, 통합·운영 브랜치와 기준 ref, 원격·로컬 차이, 미커밋 변경을 확인한다. 공통 폴더를 Git 저장소라고 가정하지 않는다.
3. 문서 저장소가 불명확하면 확인 가능한 분석을 진행하고 문서 위치에 의존하는 변경만 보류한다. 관련 없는 저장소를 임의로 선택하지 않는다.
4. 변경 대상의 원본을 백업한다. 백업과 개인 설정·계정 정보는 공유 저장소에 커밋하지 않는다.
5. 기존 정책의 관리 영역만 갱신하고 관련 없는 내용을 보존한다. 사람의 프로젝트 보정은 자동 변경하지 않는다. 보정과 새 정책이 충돌하면 해당 항목을 보고한다.
6. 읽기·발견 이후 첫 파일 변경 전에 PHASE 3의 설치용 통합 기준 워크스페이스 준비와 전용 실행 조건(1~2)을 먼저 적용한다. PHASE 2의 파일 작성은 이 워크스페이스의 설치 Worker가 수행한다. Task 정책이 이미 있으면 최소 설치 Task 등록·매핑도 먼저 수행한다.

PHASE 1 — 실제 런타임 확인
1. Paseo의 `paseo` 스킬(또는 MCP 도구 설명)로 사용 가능한 도구를 확인한다. 버전이 다른 도구·옵션·상태 이름을 추측하지 않는다. 확인 대상: `list_providers`·`list_models`·`inspect_provider`(모드·thinking 옵션 ID), `list_profiles`(프로필별 provider·model·mode·thinking·notes), `create_workspace`·`create_agent`·`archive_agent`·`get_agent_status` 지원.
2. 데몬·실행 환경 점검은 [Paseo agent lifecycle](docs/paseo-agent-lifecycle.md) 10절의 항목(데몬 관리 방식, 에이전트 셸 로케일, 프록시·API 키 환경변수 존재 여부, 로그인, relay 상태, 비밀번호 설정 여부, 도구 주입 설정, 데몬 조율 프로토콜 존재)을 따른다. 값(키·URL·비밀번호)은 출력·기록하지 않고 존재 여부만 쓴다. 이 단계는 읽기 전용이다. relay·비밀번호·CORS·플러그인 설정은 임의로 바꾸지 않고 현재 상태를 보고하며 변경은 사용자 결정이다.
3. Codex·Claude CLI 버전, 실행 호스트, 모델 접근, 도구와 추론 수준, 조직·프로젝트 설정을 확인한다. 비밀정보를 출력하거나 문서화하지 않는다.
4. 아래 모델은 기준일의 후보다. 적용 당시 공식 정보와 실제 접근을 확인하고 지원되지 않는 모델은 제외하거나 대체 결과를 기록한다. 추가 유료 크레딧 사용·구매를 자동 승인하지 않는다.
5. 현재 Root 모델, 선택한 Worker 도구, 요청 프로필·모델·thinking, 실제 실행 모델을 구분한다. 실제 실행값을 `get_agent_status`에서 확인할 수 있는지는 미확인이므로, 확인하지 못한 값은 «실행 모델 미검증»으로 기록한다. Root의 모델이 자동으로 바뀌었다고 주장하지 않는다.

POLICY A — Gitflow와 작업 위치 불변 조건
- 업무 산출물 수정·구현·테스트는 해당 저장소의 Paseo 관리 worktree 워크스페이스에서 수행한다. 통합·운영 기본 체크아웃과 `isolation: local` 워크스페이스는 기준점이며 쓰기 Worker의 작업 위치가 아니다.
- 새 업무는 해당 저장소에서 WORK_TYPE으로 결정한 기준 ref의 확정 SHA에서 `create_workspace`(`isolation: worktree`, `mode: branch-off`, 명시한 `baseBranch`, Gitflow `branchName`)로 새 워크스페이스를 만든다. 같은 업무의 후속 작업은 기존 워크스페이스를 재사용한다.
- Git 기준(ref·SHA), Paseo 프로젝트 소속, 에이전트 부모(`paseo.parent-agent-id`)는 서로 다른 사실이다. 어느 하나가 다른 하나를 증명하지 않으므로 각각 확인·기록한다.
- 기능 브랜치에서 요청해도 새 업무는 WORK_TYPE의 기준 브랜치에서 분기한다. `baseBranch`를 생략해 현재 워크스페이스 브랜치에서 분기하게 두지 않는다.
- 선택한 기준 ref·SHA를 확인할 수 없으면 실행을 중단하고 이유를 보고한다. 다른 기준 브랜치로 자동 대체하지 않는다.
- 선택한 로컬 기준과 원격 기준이 다르면 상태를 확인하고 선택한 기준을 기록한다. 최신화 명목으로 reset·강제 checkout·미커밋 변경 정리를 하지 않는다. `baseBranch`가 원격 ref를 받는지, 로컬과 원격이 다를 때 어느 쪽을 쓰는지는 미확인이므로 첫 사용에서 생성 후 HEAD 비교로 판정해 기록한다.
- 선택한 기준 ref를 resolve한 SHA와 생성한 워크스페이스의 초기 HEAD가 일치하는지 확인하고 생성 정보를 기록한다. 진행 중에 이동한 기준 브랜치 SHA와의 일치를 강요하지 않는다.
- 실제 realpath·Git 루트·브랜치·워크스페이스 ID·프로젝트 ID를 확인한다. 디렉터리 이름이나 에이전트 제목만으로 작업 위치를 판정하지 않는다. 하나라도 다르면 Worker를 배정하지 않고 보고하며 rename·reset으로 맞추지 않는다.
- 여러 저장소에 걸친 업무는 저장소별 워크스페이스로 나누고 하나의 업무 TASK_ID로 연결한다. 저장소별 기준 SHA를 기록한다. 업무 TASK_ID와 Paseo 에이전트·워크스페이스 ID는 다른 식별자이므로 구분해 매핑한다.
- Gitflow 생명주기: feature는 통합 브랜치에서 분기하여 통합 브랜치로 합친다. release는 통합 브랜치에서 분기하여 운영·통합 양쪽에 반영하고, hotfix는 운영 브랜치에서 분기하여 운영·통합 양쪽에 반영한다. 진행 중 release가 있으면 hotfix 반영 대상도 프로젝트의 기존 절차로 확인한다. release/hotfix의 운영 반영에 버전 태그를 남기는 절차도 프로젝트 관례를 따른다. 버전 태그·병합·푸시·배포는 업무의 승인 범위를 따르며 자동 실행하지 않는다.
- 위 Gitflow 네이밍과 표시 이름 계약은 정책 적용 이후 새 업무에만 적용한다. 정책 적용 전 생성된 업무의 브랜치·워크스페이스·에이전트명은 그대로 유지한다.
- 새 업무의 워크스페이스 이름(`create_workspace`)과 Worker 제목(`create_agent`, 60자 이하)은 실제 브랜치명과 맞춘다. 60자를 넘으면 줄이고 전체 이름은 원장에 둔다. 이름 변경은 내부 ID나 Git ref를 바꾸지 않는다.
- 워크스페이스 삭제(`archive_workspace`)는 worktree 삭제로 취급하며 사용자 승인 없이 하지 않는다.

POLICY B — 호스트에 중립적인 지휘와 실행
- Root(프로필 `root-orchestrator`)는 사용자 의도, 우선순위, 완료 조건, 최종 판단, 동시 실행 한도 관리를 맡는다. Coordinator(프로필 `project-coordinator`)는 Root의 자식으로 Gitflow 기준·작업 위치 확인, 모델 선택, Worker 생성·회수·정산과 아래의 최소 Task 등록 부트스트랩만 맡는다. 운영 체계를 중복 만들지 않는다.
- 각 Task 실행 단위마다 Owner는 정확히 하나다. Owner는 해당 Worker를 `create_agent`로 만든 부모 에이전트이며 Paseo의 부모 라벨이 소유 기록이다. 남의 Worker에게 업무 프롬프트를 보내거나 archive·kill·cancel하지 않고 Owner를 통해 전달한다.
- 단일 프로젝트·단일 Worker·짧고 동기적인 저위험 목표는 Root가 Coordinator를 겸해 Worker 하나를 직접 소유할 수 있다. 실제 조사·구현·문서 작성·검증은 Worker가 수행한다. 복수 프로젝트, 병렬 Worker, 장기 실행, 고위험·복잡한 조율은 Project·Goal별 Coordinator를 둔다. 정책 설명·상태 조회처럼 실행 목표가 없는 요청에는 Coordinator·Worker를 만들지 않는다.
- Codex 에이전트는 Paseo 도구가 주입되지 않은 구성에서 Root·Coordinator가 될 수 없고 Worker로만 쓴다. Codex Worker는 최종 응답으로 보고하며 Paseo worktree에서 commit하지 않는다(Git 메타데이터가 작업 폴더 밖에 있어 기본 권한 샌드박스가 거부한다). 변경 파일·diff·검증 결과를 보고하고 commit은 Claude Worker 또는 Owner가 보고된 diff 그대로 `git add <명시 파일>`로 한다. 권한 모드를 올려 우회하지 않는다. 공유 문서 담당은 가능하면 Claude Worker로 배정한다.
- 사용자가 지정한 Coordinator·에이전트·도구·모델·세션을 우선한다. 지정된 대상을 실행할 수 없으면 임의로 대체하지 않고 보고한다. 지정과 Worker 모델 선택은 별개이며 작업별 후보로 사용자 지정을 덮어쓰지 않는다. 진행 중 변경은 기존 조율 상태·미결 메시지·Worker 책임을 인계하고 실제 연결을 확인한 뒤 적용한다.
- Worker는 재위임하지 않는다. 시작 방식은 정책 규칙과 Owner의 자식 목록 점검이다. Owner는 정산 때 `list_agents`와 부모 라벨로 원장에 없는 손자 에이전트를 확인해 발견하면 보고한다. 보조 설정(custom provider 별칭 등)은 보안 경계가 아니다. 재위임은 Owner의 명시적 승인과 추적 가능한 실행일 때만 허용한다.
- Task 정책이 설치돼 있으면 최초 등록·매핑 및 누락 기록 복구에 한해 Coordinator가 검증된 문서 작업 워크스페이스에서 최소 Task README·연결표를 작성할 수 있다. 이 부트스트랩 예외는 통합/운영 기본 체크아웃 수정이나 업무 코드·최종 산출물 작성·검증을 허용하지 않는다. 등록 후 실제 업무와 후속 문서 갱신·커밋은 담당 Worker가 수행한다.
- Codex로 구현하고 Claude로 리뷰하거나 그 반대도 허용한다. 단 오케스트레이션(Root·Coordinator)은 Paseo 도구가 있는 Claude가 한다. 시스템·개발자·조직 정책과 실행 권한은 넘지 않는다.
- Paseo 관리 맥락은 설치된 프로젝트 정책과 실제 작업 맥락(부모 에이전트의 배정 메시지, 부모 라벨 `paseo.parent-agent-id`)이 함께 확인될 때만 적용한다. `PASEO_AGENT_ID` 환경 변수, 데몬·CLI 설치, MCP 도구가 보인다는 사실만으로 Paseo 업무라고 판정하지 않는다. 확인할 수 없으면 소스 수정 전에 실행 방식을 확인한다.
- Paseo 밖의 세션은 기존 전역·프로젝트 규칙을 유지한다.

POLICY C — 품질 우선 모델 라우팅 (정본: ai-agent-policy 저장소 policy/model-routing.json)
- 우선순위: 필수 고위험 전문 경로 → 프로젝트·사용자 명시 지정 → 단순 작업 조건 → 작업 유형 → 복잡도 기본값. 이미 실행 중인 Root 모델은 시작 시 선택된 모델을 사용한다. 모델 배정에 맞춰 별도 역할이나 리뷰 게이트를 추가하지 않는다.
- 프로필은 시작 구성일 뿐이다. `create_agent`에는 프로필 매개변수가 없으므로 Owner가 프로필의 provider·model·modeId·thinkingOptionId·options를 `create_agent`에 복사한다. 라우팅·시도 횟수·승격·대체 모델·동시 실행 한도는 Owner가 판정하고 이유를 원장에 기록한다.
- 프로필 값의 정본은 `policy/model-routing.json`의 `paseo_profiles`이며 `python3 -B -m ai_policy.paseo check`로 실제 프로필과 대조한다(`sync`는 사용자 승인 후 드라이런·`--plan-sha256` 절차로만, 적용 뒤 `paseo daemon reload`와 `list_profiles` 확인).
- 새 Root는 `--role root_orchestrator`, Coordinator는 `--role project_coordinator`를 사용한다. 둘 다 Paseo 호스트에서 Sonnet high이며 대체 후보가 없다(Codex는 Paseo 도구가 없어 후보에서 제외). 사용자·프로젝트 지정을 보존한다.
- LEVEL 1 단순은 명확한 소범위·자동 검증 가능·저위험을 모두 충족할 때 Luna medium(프로필 `dev-l1-simple`). LEVEL 2 일반 구현은 Luna high → Sonnet high(`dev-l2-general`)이며 계수 대상 실패 1회 뒤 두 번째 시도는 Terra high(수평 단계, 프로필 없음, 직접 구성), LEVEL 3 복잡 구현은 Sonnet high → Terra high(`dev-l3-complex`). 세부 유형은 [Orca 작업 유형별 모델 라우팅](docs/orca-model-routing.md)의 유형표를 그대로 쓴다(`orca_task_routes`는 Paseo 호스트도 공유한다).
- 리뷰는 구현자와 다른 도구 또는 독립 컨텍스트로 한다: Codex 구현 → `code_review_codex`(Claude Sonnet medium, 프로필 `review-codex-work`, 중요 시 `important_review_codex`), Claude 구현 → `code_review_claude`(Terra high → Luna high, 프로필 `review-claude-work`). 읽기 전용 규칙: Claude 리뷰어는 `plan` 모드. Codex 리뷰어는 `features.plan_mode=true`를 권장하되 도구·샌드박스 차단이 아닌 지침 수준 제한이므로 «읽기 전용이 강제된다»고 주장하지 않는다. Codex 리뷰어의 읽기 전용 증거는 리뷰 전후 대상 워크스페이스의 `git status`·diff 동일 확인(필수)이며, 변경이 생기면 리뷰를 무효로 보고한다. 쓰기 차단이 반드시 필요한 중요 리뷰(보안·무결성 등)는 Claude `plan` 모드 리뷰어를 쓴다. 리뷰어는 commit하지 않는다.
- LEVEL 4 고난도·고위험은 Opus high 또는 Sol high(`l4-critical`), LEVEL 5는 LEVEL 4에서 같은 문제를 두 번 실패한 경우에만 Fable high 또는 Astra high(`l5-last-resort`)를 사용한다.
- Codex 모델 ID는 30일 이내의 지원 모델 cache에서 계열별로 해석한다. 명시 지정은 `--resolve-family <family> --effort <effort>`로 계열과 effort를 유지한다. `pinned_fallback`이면 캐시를 갱신한 뒤 세대와 접근을 확인한다. Paseo 프로필 메모의 모델 ID와 라우터의 고정 ID가 다를 수 있으므로(원인 미확인) `list_models`와 대조한다.
- 저장소 checkout이 있으면 `python3 -B -m ai_policy.routing --host paseo --task-type <유형>`(또는 `--role`, `--level`, `--failures`, `--failure-kind`, `--available`, `--resolved`) 결과의 `action`을 먼저 확인한다. `blocked_no_available_model`(종료 40)·`handoff_to_lead`(종료 41)는 Worker를 만들지 않고 상위 Owner에 보고한다. 그 밖의 action이면 결과의 `paseo_create_agent`(`provider`, `settings.modeId`, `settings.thinkingOptionId`, 리뷰의 `settings.features`)와 `paseo_profile`(없으면 직접 구성)로 `create_agent`를 만든다. 결과 JSON을 선택 이유로 기록한다. 상위·최종 단계 모델은 `usage report` 추천이나 대체 모델로 선택하지 않는다. 명령을 쓸 수 없으면 위 규칙을 직접 적용한다.
- 승격: 같은 Worker가 검증 실패·원인 미파악·복잡도 급증으로 2회 실패하면 원인을 분류하고 독립 분석이 필요하면 직전 구현 도구에 맞는 `diagnose_codex_failure` 또는 `diagnose_claude_failure`를 사용한다. 고난도 판단이 남으면 한 단계 승격한다. 구조 위험·요구사항 모순·데이터 무결성 위험은 즉시 LEVEL 4. 환경·권한·외부 서비스·테스트 환경·모델 접근 오류와 Paseo 데몬·전달 실패는 승격하지 않고 같은 모델로 상태를 보존해 해결한다. LEVEL 4에서 다시 2회 실패하면 LEVEL 5로 올리고, LEVEL 5도 2회 실패하면 자동 승격을 멈추고 사용자에게 넘긴다. 실행 중 세션의 모델을 `update_agent`로 바꾸는 것은 승격이 아니다. 승격은 새 Worker + 구조화 인계로 한다.
- 승격 인계는 전체 대화가 아니라 목표, 관련 파일, 현재 구현 상태, 오류, 시도 내용, 실패 가설, 필요한 판단만 전달한다. 상위 모델은 분석·핵심 결정 위주로 쓰고 구현은 가능하면 Sonnet·Luna Worker가 이어받는다. 해결 뒤 후속 Worker는 원래 LEVEL의 기본 모델로 돌아간다.
- 사용 불가 모델은 설정의 대체 순서로 바꾸고 대체 사실을 기록한다. 대체 후보가 없으면 Worker를 만들지 않고 작업 상태를 보존한 채 상위 Owner에 보고한다.
- 토큰 절약: Worker에게 작업과 직접 관련된 파일·문서·설정만 전달하고, 이미 확보한 분석을 재사용하며, 같은 목표의 Worker를 중복 생성하지 않는다. 나누는 비용이 더 크면 작업을 나누지 않는다. 끝난 Worker는 정산 후 `archive_agent`로 정리하고 중간 보고는 짧게 한다. 동시 Worker는 3개, 동시 상위 모델 Worker는 1개 이하.
- 서로 다른 모델의 effort 이름과 성능을 동일하게 취급하지 않는다. 설치·접근·도구·실행 호스트가 맞는 후보만 남기고 불명확성·결합·검증 가능성·실패 영향으로 역할을 정한다.
- 유사 업무의 실제 성공 기록(`python3 -B -m ai_policy.usage report`의 추천 등)을 우선한다. 기록이 없으면 위 기본값을 쓴다. 완료한 Worker는 `ai_policy.usage record`로 기록할 수 있다.
- 브랜드별 고정 순위, 구현 언어만으로 정하는 우열, 문서·이미지 업무의 무조건적 특정 모델 선호는 만들지 않는다. API 가격을 구독 크레딧과 동일하게 계산하지 않는다.
- 작업별 선택 이유, 프로필 id, 요청값, 확인된 실행값과 접근 미검증 항목을 원장에 기록한다.

POLICY D — 실행 검사와 단일 시작 경로
1. 프로젝트에서 지원되는 시작 경로에 생성 전 검사 → 워크스페이스 생성 → 생성 결과·브랜치명 검사 → setup 성공 확인 → 정책 준비 검사 → Task 등록·실제 매핑 확정(설치된 경우) → Worker 배정 → 실제 시작 확인을 연결한다. 생성 전에는 저장소·WORK_TYPE·기준 ref/SHA·Paseo 프로젝트·지원 모델과, Task 정책이 있으면 업무 TASK_ID·문서 정본 위치·예정 브랜치를 확인한다. 아직 생성되지 않은 워크스페이스 ID·실제 업무 브랜치 매핑·신규 Task README의 존재를 생성 전 조건으로 요구하지 않는다. 생성 후에는 실제 HEAD·위치·브랜치명을, Worker 배정 전에는 Task 등록·실제 저장소별 매핑 완료를 확인한다. 기존 업무 재개는 기존 Task·매핑을 먼저 읽고 실제 워크스페이스와 대조한다.
2. Controller 역할의 에이전트가 생성 전 Gitflow 예정 브랜치명을 확정하고 `create_workspace`의 `branchName`으로 지정한다. Task 정책이 있으면 이름에 TASK_ID가 없더라도 신규 표준 연결표로 실제 브랜치와 TASK_ID를 연결한다. 이름 충돌 시 기존 브랜치를 삭제하지 않으며 안전하게 정합성을 맞출 수 없으면 배정을 중단한다. 기존 브랜치·다른 사람의 작업·원격 브랜치는 rename하지 않는다. 신규 업무에 legacy mapping 예외를 적용하지 않는다.
3. 새 워크스페이스 생성과 새 Worker 생성을 구분한다. 같은 업무를 이어갈 때 워크스페이스를 다시 만들지 않는다. Worker가 이미 있으면 중복 생성하지 않는다.
4. **정책 준비 검사**: 로컬 정책 설치가 필요한 프로젝트는 실제 작업 호스트에서 대상 워크스페이스의 진입 지침·manifest와 버전/해시·guard·선택 도구의 hook 설정 및 로딩 증거를 대조한 뒤 일반 Worker를 배정한다. 워크스페이스 생성, 정책 파일 설치, 클라이언트 신뢰, hook 실제 로딩은 서로 다른 상태다. `paseo.json` setup 훅 성공이나 생성 성공만으로 통과 처리하지 않는다. 누락은 `정책 설치 필요`로, 불일치·로딩 미확인은 구체적인 차단 사유로 기록한다. 기존 Task와 워크스페이스를 보존하고 승인된 설치 전용 경로로 넘긴다. 관련 상태가 바뀌었다는 증거를 확보한 뒤 재검사한다. 같은 조건에서 워크스페이스를 다시 만들거나 동일 배정을 반복하지 않는다. [lifecycle 4.2절](docs/paseo-agent-lifecycle.md)을 따른다. Paseo 경유 Claude 세션의 프로젝트 hook 실행 여부와 Codex 세션의 AGENTS.md 로딩은 미확인이므로 첫 사용에서 새 세션으로 확인하고 확인하지 못했으면 미검증으로 보고한다.
5. 별도 검사 스크립트가 필요하면 프로젝트의 도구 경로에 설치하고 문법·정상/거부 사례를 검증한다. 그것을 Paseo 네이티브 설정이라고 주장하지 않는다. 기준 ref 표기 정규화는 확인한 기준에 대한 refs/heads/<branch> ↔ <branch>, refs/remotes/<remote>/<branch> ↔ <remote>/<branch>만 허용하며 다른 remote·branch·revision 표현식을 기준 ref로 바꾸지 않는다. 정규화는 생성 SHA·실제 위치·담당 범위 검사를 대체하지 않는다.
6. 실제 모델·추론은 런타임의 모델 표시·응답 정보로 확인한다. 요청값(프로필 필드)만 있으면 실행 모델 미검증으로 기록한다.
7. `create_agent`·`send_agent_prompt` 수락 응답은 작업 시작의 증거가 아니다. 상태가 `running`이 되었거나 활동 기록에 해당 턴이 나타난 것을 확인해야 시작으로 보고한다. 모호한 응답에 새 Worker를 무작정 추가하지 않는다.
8. Codex·Claude가 지원하는 프로젝트 수준의 도구 실행 전 검사로 실제 작업 위치와 담당 경로를 검사한다. 기존 훅을 보존하고 문서로만 금지한 것을 실행 차단이라고 보고하지 않는다. guard의 Paseo 모드는 (1) setup 훅으로 정책 설치를 자동화 → (2) 새 세션에서 hook 실제 로딩 확인 → (3) 그 뒤에만 켠다. 1·2가 끝나기 전에 켜지 않는다. 이 설치 지시서는 guard 구현을 포함하지 않는다(별도 설계·검토 대상).
9. 검사 실패 시 일반 업무 실행과 수정을 막는다. Task 정책의 최소 등록·기록 복구와 PHASE 3에서 정의한 최초 설치·정책 복구 전용 실행만 제한된 예외로 허용한다. 어느 예외에도 기준 SHA·실제 위치·담당 범위 검사를 적용한다. 최초 설치·복구 범위 밖의 정책 누락, 통합/운영 기본 체크아웃, 잘못된 기준 SHA, 정책 누락과 무관한 setup 실패를 허용하는 폴백을 만들지 않는다.
10. 문서 지침, 시작 경로 검사, 각 도구의 수정 차단은 별개 상태로 기록한다. 지원되지 않는 차단 경로는 명시하고, 지원 불가하면 전체 강제 설치 완료라고 주장하지 않는다.

POLICY E — 작업 권한·정산·완료
- 각 업무·Worker 배정에 목표, 관련 저장소·워크스페이스, 담당 파일·책임, 인터페이스, 제약, 완료 조건, 보고 형식(데몬 프로토콜의 `PROJECT_DONE:`/`BLOCKED:`/`NEED_APPROVAL:` + 증거)을 지정한다.
- project-task-policy가 설치돼 있으면 업무 TASK_ID와 문서 정본을 먼저 확인하고, 이 정책에서 만든 각 저장소의 WORK_TYPE 기준 워크스페이스·실제 브랜치·기준 SHA를 업무 연결표에 등록한 뒤 Worker를 배정한다. 연결표에는 Paseo agentId·workspaceId를 로컬 실행 기록으로 연결하며 팀 공유 문서에는 저장소·브랜치·TASK_ID·확인된 커밋만 둔다. Task 등록·브랜치 매핑·문서 커밋 조건을 완료 검사에 포함한다.
- project-task-policy가 없으면 해당 설치를 요구하거나 문서 저장소·docs/tasks를 자동 생성하지 않는다. 이 지시서의 실행 규칙만 적용한다. 설치 순서와 관계없이 기존 Task 정책의 관리 블록·정본·프로젝트 보정을 보존한다.
- Task 정책이 있으면 배정 시 Task README·공용 색인 담당 Worker를 명시하고 문서 저장소의 작업 워크스페이스·허용 경로를 전달한다. 다른 Worker는 담당 범위의 변경·검증·커밋·인계 요약을 Owner에게 보고하고 Owner는 문서 담당자에게 회수 결과를 전달한다. Owner가 후속 공유 문서를 대신 쓰거나 비담당 Worker가 Task README를 직접 편집하지 않는다. 체크포인트 기록·문서 커밋 증거는 문서 담당자의 실제 반영 결과로 확인한다. 문서 담당이 Codex Worker이면 내용 작성·검증까지만 하고 commit은 Claude Worker 또는 Owner가 보고된 내용 그대로 한다.
- 동일 파일을 수정하는 권한은 한 Worker에게만 둔다. 읽기 전용 리뷰어는 위 POLICY C의 규칙(Claude `plan` 모드, Codex는 지침 수준 + 무변경 검사)을 따른다.
- 기본은 Worker 1개다. 독립적인 작업만 3개 이하로 병렬화한다. 같은 파일·DB 영역·공통 생성 산출물·API 계약은 분리하거나 순차 실행한다. 워크스페이스 격리가 DB·포트·외부 시스템 격리는 아니다.
- 다른 Worker의 변경을 되돌리지 않는다.
- 동일 실행자가 같은 원인에 대해 수행하는 구현·수정은 최초 시도와 새로운 증거·다른 가설에 따른 추가 수정 1회, 총 2회까지다. 두 번째 실패 후 자동 재시도를 중단하고 증거를 책임자에게 전달한다. 모델 교체만으로 시도 횟수를 초기화하지 않는다. 구조적 위험·요구사항 모순·데이터 무결성 위험은 즉시 책임자에게 전달한다.
- Paseo 실행 재시도: 도구·환경·권한·외부 서비스·Worker 중단·데몬 재시작으로 인한 `closed`·메시지 유실·알림 미도착·권한 요청 대기처럼 모델 판단이 아닌 실행 실패는 같은 원인에 대해 최초 실행을 포함해 최대 3회까지 같은 모델로 상태를 보존하며 재실행한다. 3회째도 실패하면 모델을 승격하지 않고 증거를 상위 Owner에 넘긴다.
- 완료 알림은 «턴이 끝났다»는 신호이지 업무 완료가 아니다. 알림은 중복될 수 있으므로 원장으로 이미 처리한 결과를 거른다. 결과와 검증 근거를 확보하고 Worker가 `running`이 아님을 확인한 뒤 `archive_agent`로 정리하고 정리 상태를 기록한다. 실행 중·불확실·미정산·사용자 소유·기존 세션은 정리하지 않는다. 정산 절차·Owner 장애 인계·데몬 재시작 대응은 [Paseo agent lifecycle](docs/paseo-agent-lifecycle.md) 5·8·9절을 따른다.
- 대기는 알림 기반으로 하고 턴을 끝낸다. 반복 폴링을 하지 않는다.
- 기존 Worker의 종료·잔여 쓰기 상태가 불확실하면 새 쓰기 Worker로 교체하지 않는다. 타임아웃만으로 교체하지 않는다.
- 완료는 요구사항, 실제 검증 결과, 통합 동작, 담당 범위와 남은 위험으로 판단한다. 수락·시작·실행 중·검토 대기·완료·실패·미확인을 구분한다.
- 인증·인가, 암호화, 파괴적 DB 작업, 운영 인프라와 데이터 손실 위험은 선택한 전문 실행자 Sol high 또는 Opus high의 분석·검토 및 정확한 대상·복구·무결성 확인을 먼저 거친다. 양쪽 계열의 검토를 모두 의무화하지 않으며 설계 위험이 크거나 실패 영향이 매우 크면 독립 전문가 검토를 추가한다. 상위 지침이 특정 모델·검토를 요구하면 그 제한을 따른다.
- 장시간 실행 프로세스와 로그(2026-11-04, 로컬 백엔드 bootRun 출력·Gradle 데몬 로그가 각각 70GB 넘게 쌓여 디스크가 96% 찬 사례): 서버·watch의 표준출력을 크기 제한 없는 파일에 통째로 받지 않고 크기 제한이 있는 앱 로그에 남기며 출력 파일은 크기를 주기적으로 확인한다. Gradle로 서버를 띄울 때(`bootRun` 등)는 `--no-daemon`을 붙인다(데몬 로그 `~/.gradle/daemon/<버전>/daemon-*.out.log`는 콘솔 출력을 크기 제한 없이 복사하고 서버를 멈춰도 지워지지 않으며 14일 뒤 정리된다). SQL 결과 전체를 찍는 로그(log4jdbc `jdbc.resultsettable` 등)는 켜지 않거나 필요할 때만 잠깐 켜고 크기 제한이 있는 파일에만 남기며 콘솔에는 info 이상만 보낸다. 로그에는 업무 데이터·개인정보가 들어갈 수 있으므로 작업이 끝나면 직접 띄운 서버를 멈추고 임시 로그를 정리하며 남겨야 하면 로컬 작업 기록 폴더에만 둔다. 작업 완료·보고 시 직접 띄운 백그라운드 프로세스와 그 로그 크기를 함께 보고한다. Worker 시작 문맥에도 이 규칙을 전달한다.
- 기존 프로젝트의 Human Gate를 보존한다. 설치 요청이 운영 실행·배포·통합 브랜치 병합·워크스페이스 삭제의 포괄 승인은 아니다. 다음 Paseo 특유 행위는 Human Gate 항목으로 사용자 결정을 받는다: relay 사용 여부(켜기·유지·끄기), 비밀번호·CORS 변경, 플러그인 설치, schedule 생성(비용 발생), 권한 모드 상향(Claude `bypassPermissions`, Codex `full-access`), `archive_workspace`. 권한 요청 승인·완료 알림·에이전트 상태는 Task 범위의 사용자 승인이 아니다.

PHASE 2 — 문서와 루트 진입 연결
1. 기존 AI_CONTEXT.md, PROJECT_RULES.md, BUILD_AND_TEST.md, 기존 작업 흐름 문서(예: ORCA_WORKFLOW.md)를 우선 재사용한다. 없으면 설치에 필요한 실제 근거만 조사하고 부족한 항목을 UNKNOWN으로 기록한다.
2. POLICY_DIR에 PASEO_POLICY.md, MODEL_ROUTING.md, WORKTREE_RULES.md, INSTALLATION.md를 생성한다. 위 정책을 프로젝트의 실제 경로·검증된 명령·모델 후보에 맞춰 작성한다. 병행기 동안 기존 ORCA_POLICY.md 등 Orca 산출물은 삭제하지 않는다.
3. 문서 첫 줄에 generated-by: paseo-project-policy@v0.1.0-draft와 생성일을 주석으로 기록하고, 마지막에 프로젝트 보정 섹션을 둔다. GENERATED.md에 상대 경로·버전·생성일·보정 상태를 기록한다. 기존 산출물 행을 보존한다.
4. 미추적 AGENTS.md와 CLAUDE.md에는 paseo-project-policy:begin/end 관리 블록만 추가하거나 갱신한다. 기존 orca-project-policy 블록은 병행기 동안 그대로 둔다. 기존 추적 진입 파일은 위 비추적 계약에 따라 지원되는 로컬 진입·설정으로 분리한다. 기존 진입 파일과 내용을 보존한다. 적용되지 않는 AGENTS.override.md나 프로젝트 설정이 있는지도 확인한다.
5. CLAUDE.md는 상대 경로의 @import로 핵심 정책을 연결한다. AGENTS.md에는 첫 업무 행동으로 핵심 정책을 실제로 끝까지 읽고 적용하라는 규칙과 상대 경로를 둔다. Markdown 링크가 자동 import라고 가정하지 않는다. Paseo의 Claude 에이전트가 CLAUDE.md를 읽는지(SDK 설정 소스)와 Codex 에이전트가 AGENTS.md를 읽는지는 새 세션에서 확인한다(Codex는 미확인).
6. 여러 저장소에서는 설치 정책 정본을 확인한 로컬 정책 위치에 두고 각 저장소에는 버전이 고정된 미추적 정책 사본 또는 검증된 로컬 스냅샷과 진입 연결을 설치한다. 원본 지시서의 버전·해시와 로컬 경로를 확인한다. 다른 작업 워크스페이스의 변경 가능한 문서를 직접 참조하지 않는다.
7. Worker 시작 문맥(`create_agent`의 `initialPrompt`)에 Worker 역할과 재위임 제한, 정책 버전, 관련 Task, 워크스페이스 ID, 기준 SHA, 담당 경로, 완료 조건, 보고 형식을 전달하고 지침 읽기를 확인한다.
8. `paseo.json`에는 실제 버전이 지원하는 설정(setup 훅)만 둔다. 가상의 스키마로 강제를 구현했다고 주장하지 않는다. setup 훅으로 정책 설치를 자동화할 수 있는지와 실패 시 동작은 미확인이므로 첫 사용에서 확인한다.
9. 전역 Codex AGENTS.md·config.toml과 Claude CLAUDE.md·settings.json, `~/.paseo` 설정은 수정하지 않는다. 세션마다 GitHub를 다운로드하는 훅이나 불필요한 시작 훅은 추가하지 않는다.

PHASE 3 — 로컬 설치 부트스트랩과 워크스페이스 전파
1. 설치 파일 변경도 해당 저장소의 통합 기준 Paseo worktree 워크스페이스에서 수행한다. 이 설치 전용 경로는 Paseo 정책 자체의 최초 설치·복구뿐 아니라 함께 사용하는 Task 정책의 설치·갱신에도 적용한다. 기존 로컬 설치·로딩이 미완료라면 같은 설치 업무의 검증된 워크스페이스를 재사용하거나 이 경로로 새 설치 전용 워크스페이스를 준비한다. 일반 업무 실행 허용이나 승인 없는 통합 브랜치 병합으로 대체하지 않는다. 최초 설치·정책 복구 전용 실행은 일반 업무와 구분한다. Root·Coordinator가 읽은 설치 지시서의 버전·출처와 누락 파일, 허용 경로·수정 범위·종료 조건을 확정하여 설치 Worker(Claude 권장, Codex는 commit 불가)에게 전달한다. 설치 Worker는 아직 없는 정책 파일 대신 이 검토된 지시서를 읽고 시작할 수 있다.
2. 설치 전용 실행에 한해 생성 예정 정책·진입·검사 파일의 부재와 그 부재만으로 실패한 정책 로딩 검사를 일시 허용한다. setup 실패도 해당 파일 부재만이 원인이라고 확인한 경우에 한정하며 원인 미확인은 허용하지 않는다. 통합 기준 ref/SHA·실제 위치·기존 권한·필수 실행 환경 검사는 통과해야 한다. 허용 수정은 정책·템플릿·진입 파일·관련 검사 파일과 Task 정책이 있으면 최소 설치 Task 기록뿐이다. 업무 소스·DB·운영 변경은 금지한다.
3. 설치 Worker는 파일 생성 후 정책·import·검사를 다시 확인한다. 전용 실행이 끝나면 예외는 종료되며 일반 업무에 전파하지 않는다. 설치 기록에 예외 사유·허용 경로·검사 결과를 남기고 기존 훅을 전역 해제하거나 일반 시작 경로에 무조건 우회 옵션을 만들지 않는다. 실제 런타임에서 이 제한된 실행을 지원할 수 없으면 차단 상태와 필요한 설정을 보고한다.
4. 설치 변경은 비공개 로컬 diff·manifest·백업으로 검토하고 Git 비추적 여부를 확인한다. 실제 공유 업무 문서의 커밋과 로컬 설치 기록은 분리한다.
5. 새 업무 워크스페이스의 setup에 검증된 로컬 설치 산출물 준비·버전/해시 확인·지침 로딩·guard 검사를 연결한다. 자동 setup이 미지원이면 검증된 설치 전용 경로로 준비한 뒤 Worker를 배정한다.
6. 통합 기준 feature/release뿐 아니라 운영 기준 hotfix 워크스페이스에서도 미추적 정책·검사기·진입 파일과 정본 접근을 검증한다. 파일 설치나 Git checkout만으로 정책이 상속됐다고 간주하지 않는다.
7. 정책 파일 사본은 정본 버전·해시와 비교 가능하게 관리하고, 재설치 시 프로젝트 보정과 개인 진입 내용을 보존한다.

PHASE 4 — 수용 검증
- 문서 경로·import·관리 블록·명령 지원·스크립트 문법과 기존 설정 보존을 확인한다. 설치 manifest 전체의 Git 비추적·ignore·staging 제외 및 새 워크스페이스 재설치도 검증한다.
- ref 표기 검사: 전체/축약형 조합의 동일 기준 ref를 허용하고 로컬/원격 기준 ref 불일치, 다른 remote·branch·잘못된 표기, 잘못된 SHA·위치를 거부한다.
- 역할 검사: 단일 프로젝트·단일 Worker·짧고 동기적인 저위험 목표에서는 Root가 Coordinator를 겸해 Worker를 직접 소유할 수 있는지 확인한다. 복수 프로젝트·병렬·장기·고위험 작업에는 별도 Coordinator가 유지되는지 확인한다. 사용자 지정이 우선되고 Worker 선택과 분리되는지도 확인한다. 지정된 대상을 실행할 수 없으면 임의 대체 없이 보류한다. 실행하지 않은 항목은 미검증으로 기록한다.
- 정상 검사: feature/release는 통합 기준, hotfix는 운영 기준의 SHA로 생성한 업무 워크스페이스를 허용한다. 유형과 prefix·기준 역할 불일치는 거부한다. Task 정책이 있으면 생성 전 실제 워크스페이스 ID 부재는 허용하되 Worker 배정 전 실제 매핑 누락은 거부한다. 신규 Gitflow 브랜치와 TASK_ID 연결표, 워크스페이스·Worker 제목과 브랜치명의 일치를 확인한다. 기존 업무 이름 보존도 확인한다.
- 최초 설치·복구 검사: Paseo 뒤 Task 정책 설치와 로컬 설치 미완료 상태의 추가 설치도 설치 전용 경로를 따르는지 확인한다. 정책 파일이 없는 설치용 통합 기준 워크스페이스에서 제한된 설치 Worker 시작·파일 작성만 허용하고 범위 밖 수정과 일반 업무 시작을 거부한다. 파일 생성 후 재검사·예외 종료를 확인한다.
- 거부 검사: 일반 업무에서는 통합/운영 기본 체크아웃, 다른 초기 기준 SHA, 누락된 정책, setup 실패를 거부한다. 실제 작업 중 이동한 기준 브랜치와의 SHA 차이는 거부 사례가 아니다.
- 조합 검사: Coordinator의 검증된 문서 작업 워크스페이스 내 최소 Task 등록은 허용하되 등록 전 업무 구현·통합/운영 기본 체크아웃 수정은 거부한다. 등록 후 Worker가 직접 실행하고 승인 없는 재위임은 거부한다(Owner의 자식 목록 점검 확인). 고위험 후보 선택이 양쪽 계열의 필수 중복 검토를 만들지 않는지 확인한다.
- 병렬 기록 검사: 같은 업무의 비담당 Worker 결과가 Owner를 통해 문서 담당자에게 전달·반영되고 공용 README 동시 쓰기를 거부하는지 확인한다.
- 교체 검사: 타임아웃만으로 교체는 거부하고, 확인된 대상 실행 종료·잔여 쓰기 부재·필수 정리 후에만 새 쓰기 Worker를 허용한다. 수동 종료도 같은 기준으로 확인한다.
- Codex 구현 → Claude 리뷰어(`plan`), Claude 구현 → Codex 리뷰어(`plan_mode` 권장 + 리뷰 전후 `git status`·diff 무변경 검사)를 배정할 수 있는지 확인한다. 접근·과금·호스트 조건상 실제 실행하지 못한 항목은 미검증으로 기록한다.
- 새 일반 세션과 새 통합 기준 워크스페이스에서 실제 지침 로딩·실행 위치·모델을 확인한다. 원본 통합/운영 체크아웃에 실제 쓰기를 시도해 검증하지 않는다.
- Pilot 검증이 사용자 작업 범위에 포함되면 작은 읽기 전용 업무로 수행한다. 실제 Worker 생성·호출을 하지 않은 경우 문서·정적 검사만 통과했다고 보고한다.
- 비즈니스 기능·운영 DB·배포에는 설치 검증을 위해 변경을 가하지 않는다.

FINAL REPORT
프로젝트·저장소 매핑, WORK_TYPE·통합/운영 매핑·기준 ref/SHA, 설치 파일·백업 위치·버전, 후보와 확인한 실제 모델(요청 프로필·값과 확인값 구분), 기존 지침 보존, 지원되는 차단 경로와 제한, 설치 산출물 Git 비추적/기존 추적 해제 대기 여부, 새 세션·워크스페이스 재설치 검증, 데몬 점검 결과(기준선과 다른 항목만), 미검증 항목과 다음 조치를 간단히 보고한다.

완료를 로컬 파일 설치 완료 / Git 비추적 확인 완료 / 새 워크스페이스 로딩 검증 완료 / 실행 차단 검증 완료로 나눠 표시한다. 필요한 조건을 충족하지 못했으면 전체 설치 완료라고 주장하지 않는다.

위 범위의 읽기·백업·프로젝트 문서·진입 연결·지원되는 검사 설치는 승인한 것으로 진행해줘. 대상이나 문서 위치가 불명확하면 독립적인 분석을 먼저 진행하고 해당 의존 작업에 필요한 정보만 요청해줘.
```

## 운영 예시

```text
Root orchestrator (Claude, 프로필 root-orchestrator)
└── Project coordinator (Claude, 프로필 project-coordinator)
    ├── task-a 워크스페이스 → Codex / Luna (LEVEL 1, dev-l1-simple)
    ├── task-b 워크스페이스 → Claude / Sonnet (LEVEL 2·3, dev-l3-complex)
    └── task-c 워크스페이스 → Opus 또는 Sol (승격·고위험만, l4-critical)
```

Worker의 도구는 오케스트레이터의 도구와 달라도 됩니다(오케스트레이터는 Paseo 도구가 있는 Claude). 모델 선택, Git 기준, Paseo 프로젝트·부모 에이전트 관계, 실제 실행 호스트는 각각 검증합니다. 이 지시서를 다시 실행할 때는 설치 버전과 변경 diff를 확인하고 프로젝트 보정 내용을 유지하세요.
