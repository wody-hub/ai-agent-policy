# AI Agent Policy

AI에게 개발 업무를 맡길 때 **누가 일을 할지, 어디에서 작업할지, 무엇을 기록할지**를 정해주는 지침 모음입니다. Codex와 Claude Code의 모델 선택, Paseo의 작업공간, 프로젝트의 업무 기록을 네 파일로 나누었습니다.

> **조율 도구 전환(2026-11-25 결정).** 조율 도구는 Orca에서 Paseo로 옮깁니다. 새 Task는 Paseo 규칙을 따르고, 기존 Orca 파일(`orca-project-setup.md`, `docs/orca-*.md`, `policy/orca-common.md`, `--host orca`)은 **병행기 동안 보관**합니다. 병행기에는 Orca가 이미 소유한 진행 중 Run·worktree만 Orca 규칙으로 마무리하고, 모든 Orca Run이 정산되면 보관 상태로 확정합니다. 상세는 [이전 설계](docs/paseo-migration-design.md)를 보세요. Hermes는 사용하지 않습니다.

필요한 파일을 AI에게 읽히고 설치를 요청하면, 이후 작업에서 따라야 할 지침과 지원되는 설정을 구성합니다. 아래에서 각 파일이 어떤 상황에 필요한지 설명하고, 뒤쪽에서 상세 운영 전략을 다룹니다.

기준일: **2026-10-07** · 모델 라우팅: **1.6.0**(2026-11-25, Paseo 호스트 추가, Orca 값은 1.5.0과 동일) · Paseo 설치 지시서: **v0.1.0-draft**(2026-11-25, 사용자 승인 전 초안) · 단독 도구 전략: **1.4.0** · Orca 단일 Worker 조율 경량화: **2026-11-09**(보관). 모델·추론 수준·실행 기능은 계정과 제공자, 설치 버전에 따라 달라지므로 적용할 때 다시 확인합니다.

## 파일 설명과 설치 방법

**필요한 정책만 골라 설치하세요.** 아래 네 파일은 AI에게 전달하는 설치 지시서입니다. 하나만 설치하면 해당 영역만 적용되고, 함께 설치하면 연동됩니다. README는 설명 문서이며 필수 설치 입력은 아닙니다.

| 어떤 목적에 쓰나요? | 설치 파일 | 적용되는 곳 |
| --- | --- | --- |
| Codex가 작업에 맞는 모델을 고르고 역할을 나누도록 하기 | [Codex 설치 파일](codex-global-model-routing-prompt.md) | 내 Codex의 공통 지침 |
| Claude Code가 작업에 맞는 모델을 고르고 역할을 나누도록 하기 | [Claude Code 설치 파일](claude-code-global-model-routing-prompt.md) | 내 Claude Code의 공통 지침 |
| Paseo에서 업무마다 별도 작업공간을 사용하고 두 도구의 모델을 선택하기 | [Paseo 설치 파일](paseo-project-setup.md) (초안) | 설치한 프로젝트 |
| (보관, 병행기) Orca에서 같은 목적 | [Orca 설치 파일](orca-project-setup.md) | 병행기 동안 기존 Orca Run을 마무리하는 프로젝트 |
| AI가 업무 내용·변경·검증 결과를 기록하고 Git 이력으로 남기기 | [Task 관리 설치 파일](project-task-policy-setup.md) | 설치한 프로젝트와 문서 저장소 |

### 1. Codex — 작업에 맞게 AI의 역할을 나누는 지침

Codex로 개발할 때, 어떤 작업을 직접 처리하고 어떤 작업을 다른 AI 작업자에게 맡길지 정합니다. **전체 요구사항과 최종 결과를 책임지는 역할**, **명확한 기능을 구현하는 역할**, **어려운 문제를 분석하는 역할**을 나누고, 상황에 맞는 모델을 선택하도록 합니다. AI 작업자는 메인이 맡긴 범위를 조사하거나 구현하는 별도 에이전트를 뜻합니다.

예를 들어 “상품 목록에 검색과 페이지 이동을 추가해줘”라고 요청하면, 메인은 요구사항과 완료 기준을 정하고 구현 담당자가 개발·검증을 수행한 뒤 메인이 결과를 확인하는 방식을 사용할 수 있습니다. 짧은 문구 수정처럼 나누는 비용이 더 큰 작업은 직접 처리합니다. 같은 실패를 반복하면 무엇이 실패했는지 정리하고 책임자가 다시 판단하도록 합니다.

**Codex를 사용하는 사람이 설치하면 좋습니다.** 사용자 공통 지침에 설치하므로 프로젝트마다 같은 내용을 다시 입력하는 일을 줄이고, 새 일반 세션에서 읽히도록 구성합니다. 실제 사용 가능한 모델과 설정은 설치할 때 확인합니다.

### 2. Claude Code — Claude 모델들의 담당 업무를 정하는 지침

Claude Code에서 작업을 맡길 때, **전체 판단·검토를 맡을 모델과 기능 구현·단순 조회를 맡을 모델의 역할**을 정합니다. 명확한 개발은 구현 담당자가 맡고, 원인이 불분명하거나 여러 부분이 얽힌 문제는 전문 분석을 맡도록 안내합니다. 중요한 결정에는 필요한 경우 별도의 의견을 구합니다.

예를 들어 “재현되는 화면 오류를 수정해줘”라는 요청은 구현과 관련 검증을 한 담당자에게 맡길 수 있습니다. 수정 범위가 불명확하거나 데이터 처리 방식부터 판단해야 하는 경우에는 먼저 원인을 분석합니다. 작업을 나눴다는 이유만으로 결과를 완료로 보지 않고, 실제 변경과 검증 결과를 확인하도록 합니다.

**Claude Code를 사용하는 사람이 설치하면 좋습니다.** 사용자 공통 지침과 지원되는 모델 설정·개인 에이전트에 적용합니다. Codex 지침과 목적은 같지만 설치 대상 도구가 다르므로, 두 도구를 모두 사용한다면 각각의 도구에 해당 파일을 설치합니다.

### 3. Paseo — 업무마다 작업 위치를 분리하고 실행할 AI를 고르는 지침

Paseo로 프로젝트를 관리할 때, **새 업무는 Gitflow 유형에 맞는 기준 브랜치에서 출발한 별도 워크스페이스(worktree)에서 진행**하도록 정합니다. 여기서 워크트리는 같은 Git 저장소의 다른 브랜치를 별도 폴더에서 작업하는 방식입니다. 기능·릴리스는 통합(`dev`/`develop`), 긴급 수정은 운영(`main`/`master`) 브랜치에서 분기하며, Git 기준·Paseo 프로젝트·에이전트의 부모를 각각 확인합니다.

예를 들어 검색 기능과 주문 화면을 동시에 개발하면, 각 업무를 별도 워크스페이스와 담당자(Worker)로 나누어 진행합니다. 같은 업무를 이어갈 때는 기존 워크스페이스를 재사용합니다. 다만 작업 폴더가 나뉘어도 DB나 서버 포트는 공유될 수 있으므로 별도로 확인합니다.

또한 **작업에 맞는 Codex·Claude 모델을 하나의 후보군에서 선택**합니다. 오케스트레이터(Root·Coordinator)는 Paseo 도구가 있는 Claude가 맡고, Worker는 Codex일 수도 Claude일 수도 있습니다. 선택한 프로필·모델과 실제 실행 상태를 따로 확인하며, 프로필은 시작 구성일 뿐 라우팅·승격·동시 실행 한도는 Owner가 판정합니다.

**Paseo를 사용해 업무를 나누거나 여러 저장소를 함께 관리할 때 설치하면 좋습니다.** 프로젝트별로 적용하므로 사용할 프로젝트마다 설치합니다. 설치 지시서는 아직 사용자 승인 전 초안입니다.

### 4. Task 관리 — AI가 한 일을 다음 사람도 알 수 있게 남기는 지침

AI가 실제 업무를 시작하기 전에 **업무 ID, 요청 내용, 완료 기준, 담당 범위, 작업 브랜치**를 기록하고, 진행 중 변경 사항과 검증 결과를 갱신하도록 정합니다. 여기서 Task는 하나의 업무와 그 기록을 뜻합니다. “무엇을 요청했고, 어디를 바꿨고, 어떻게 확인했는지”를 나중에도 찾을 수 있게 만드는 목적입니다.

예를 들어 “상품 검색 기능 추가” 업무를 맡기면, 같은 업무 ID로 코드 브랜치와 문서를 연결합니다. 다른 AI나 사람이 이어받아도 해당 기록에서 요구사항, 진행 상태, 확인한 결과와 남은 문제를 볼 수 있게 합니다. 완료 보고 전에 관련 문서를 Git의 로컬 커밋으로 남기고, 검증이나 문서 커밋이 보류됐으면 그 상태를 정확하게 알리도록 합니다. 원격 업로드·병합·배포는 해당 업무에서 승인한 범위를 따릅니다.

여러 저장소를 묶어 관리하는 프로젝트는 지정한 **문서 저장소**에 기록을 모읍니다. 단일 저장소 프로젝트는 기존 문서 경로를 우선하고, 없으면 내부 `docs/tasks/`를 사용합니다. 여러 AI가 같은 업무를 진행할 때는 문서 담당자를 정해 결과를 모아 기록합니다.

**AI의 작업을 추적하거나 팀·다른 세션에 인계해야 하는 프로젝트에 설치하면 좋습니다.** Paseo 없이도 사용할 수 있습니다. Paseo와 함께 설치하면 업무 기록에 실제 워크스페이스와 브랜치를 연결합니다. 단순 질문만 하는 대화에는 새 업무 폴더를 만들지 않습니다.

### 무엇부터 설치하면 좋을까요?

Codex만 사용하면 Codex 파일부터, Claude Code만 사용하면 Claude 파일부터 설치하세요. 두 도구를 모두 쓰면 각각 설치하면 됩니다. 작업 기록도 남기고 싶다면 프로젝트에 Task 관리 파일을 추가하고, Paseo를 사용한다면 Paseo 파일도 추가합니다.

예를 들어 네 정책을 모두 사용하는 프로젝트에서 “상품 검색을 추가해줘”라고 요청하면, 업무 ID와 기록 위치를 정하고 → dev 기준 작업공간을 준비하고 → Task와 실제 브랜치를 등록하고 → 담당 AI가 구현·검증하고 → 문서 담당자가 결과를 기록·커밋한 뒤 완료 여부를 보고하는 흐름입니다.

### 빠른 설치

1. 위 링크에서 필요한 파일을 내려받거나, 아래 명령으로 저장소를 복제합니다. 복제한 저장소는 설치 지시서를 보관하는 위치이며 프로젝트 정책을 설치할 대상은 별도로 지정합니다.

   ```bash
   git clone https://github.com/wody-hub/ai-agent-policy.git
   ```

2. Codex·Claude 전역 정책은 해당 도구에서 파일 안의 **설치 프롬프트 코드 블록 전체**를 입력합니다. 또는 파일을 첨부하거나 로컬 경로로 읽게 한 뒤 아래 요청을 사용합니다.
3. Paseo·Task 정책은 **적용할 프로젝트**에서 요청합니다. 프로젝트 그룹이면 대상 저장소들과 문서 저장소를 함께 알려주세요. 파일별로 순서대로 설치하고 설치 보고를 확인합니다.
4. 설치 후 새 세션을 열어 AI가 지침을 읽었는지, 어떤 모델과 설정이 적용됐는지 확인합니다. Paseo는 설치 산출물이 Git 비추적인지, 새 워크스페이스에 로컬 재설치한 지침이 읽히는지 확인합니다. Task 관리는 작은 업무 하나로 등록·브랜치 연결·검증 기록·문서 커밋까지 확인합니다. 아직 실행하지 않은 확인 항목은 설치 보고에 미검증으로 남깁니다.

파일을 읽게 한 뒤 사용할 요청 예시입니다. 해당 파일 한 개를 선택해 요청하세요.

| 선택한 파일 | 요청 예시 |
| --- | --- |
| Codex 전역 | 이 파일을 끝까지 읽고 내 Codex 전역 모델 운영 지침으로 설치해줘. 기존 설정을 백업·보존하고 새 세션의 적용 방식과 실제 확인 결과를 알려줘. |
| Claude 전역 | 이 파일을 끝까지 읽고 내 Claude Code 전역 모델 운영 지침으로 설치해줘. 기존 설정을 백업·보존하고 새 세션의 적용 방식과 실제 확인 결과를 알려줘. |
| Paseo 프로젝트 (초안) | 이 파일을 끝까지 읽고 현재 프로젝트에 Paseo 전략을 설치해줘. 기존 전역 지침을 유지하고 Gitflow 기준·워크스페이스·지원 기능을 확인한 뒤 설치 상태를 구분해 알려줘. |
| Task 프로젝트 | 이 파일을 끝까지 읽고 현재 프로젝트에 Task 관리 정책을 설치해줘. 문서 정본 위치와 브랜치 연결을 확인하고, Paseo 정책이 있으면 연동하고 없으면 Task 정책만 설치해줘. |

파일을 읽거나 저장소를 내려받는 것만으로 설치되지는 않습니다. 에이전트가 파일 안의 설치 지시를 수행해야 적용됩니다. 범용 자동 설치·업데이트 스크립트는 제공하지 않습니다. 기존 설치를 갱신할 때도 최신 파일을 다시 적용하고 변경 diff와 보고를 확인합니다.

### 네 정책의 독립 설치와 조합

각 파일은 독립적으로 설치할 수 있습니다. 모두 사용할 경우 역할이 맞물리며, 빠진 정책을 자동 설치하거나 그 정책이 있다고 가정하지 않습니다.

| 설치한 정책 | 동작하는 범위 | 추가하지 않는 동작 |
| --- | --- | --- |
| Codex만 | Codex 모델·추론·위임 전략 | Claude 설정, Paseo 워크스페이스, Task 폴더 설치 |
| Claude Code만 | Claude 모델·추론·개인 에이전트 전략 | Codex 설정, Paseo 워크스페이스, Task 폴더 설치 |
| Paseo만 | Gitflow 기준 워크스페이스와 사용 가능한 모델 후보 배정 | 전역 모델 지침 변경, 별도 Task 문서 정책 설치 |
| Task만 | 업무 기록·문서 정본·브랜치 연결·허용된 문서 커밋 | dev 강제, Paseo 실행, 모델 설정 변경 |
| 네 정책 모두 | 모델 선택 + Gitflow 작업공간 + 업무 추적·문서 커밋 | 설치 범위를 넘는 자동 게시·병합·배포 |

권장 설치 순서는 사용하는 도구의 전역 정책 → 프로젝트 Paseo 정책 → Task 정책입니다. 다른 순서로 설치해도 관리 블록과 담당 영역을 보존해야 합니다. 두 전역 정책은 해당 CLI를 사용하는 경우에만 적용됩니다. Paseo에서는 프로젝트의 교차 도구 구현 배정 정책이 더 구체적으로 적용되며, 시스템·개발자·조직 제한은 그대로 따릅니다.

적용 시 Paseo 관리 업무 여부(부모 에이전트의 배정 메시지와 부모 라벨 `paseo.parent-agent-id`. `PASEO_AGENT_ID` 환경 변수만으로는 판정하지 않음)와 현재 역할(Root·Coordinator·Worker)을 먼저 확인합니다. 상위 지침을 지키면서 모델 운영은 해당 전역 정책, Paseo 실행 위치·역할·통합 후보 선택은 Paseo 정책, 업무 기록·브랜치 연결·문서 커밋은 Task 정책을 따릅니다. Worker에게 지휘자의 배정 규칙을 재귀적으로 적용하지 않습니다.

조합 실행은 `업무 ID 결정 → 문서 위치 확인 → 업무 유형별 기준 워크스페이스 생성·검사 → Task 등록·브랜치 매핑 → Worker 배정 → 구현·검증 → 기록 갱신·문서 커밋 → 결과 보고`입니다. 최초 Task 기록을 위한 문서 작업공간 준비와 최소 등록·매핑은 부트스트랩으로 허용합니다. Paseo에서는 Coordinator가 검증된 문서 작업 워크스페이스에서 이 최소 기록만 작성할 수 있으며, 통합/운영 기본 체크아웃 수정과 등록 전 업무 코드·최종 산출물 수정·검증은 허용하지 않습니다.

## 공통 운영 원칙

비용이 낮은 모델의 호출 횟수를 늘리는 것보다 **정확성을 유지하면서 전체 사용량과 완료 시간을 줄이는 것**을 목표로 합니다. 전체 비용에는 실행, 맥락 전달, 재시도, 검토, 통합이 모두 포함됩니다.

- 작고 명확한 단일 프로젝트·단일 Worker·저위험 작업은 Paseo에서 Root가 Coordinator 역할을 겸해 Worker를 직접 소유할 수 있습니다. 복수 프로젝트·병렬·장기·고위험 작업에는 별도 Coordinator를 둡니다. Paseo 업무의 실제 수정·검증은 항상 Worker가 수행합니다.
- 목표·완료 조건·인터페이스가 명확하고 검증 가능한 기능은 실행자에게 맡깁니다. 파일 수만으로 승격하지 않습니다.
- 불명확한 원인, 공유 상태, 동시성, 구조 변경과 높은 실패 영향은 전문 판단이 필요한 작업으로 분류합니다.
- 일반 인계에는 목표, 관련 맥락, 담당 파일·책임, 인터페이스, 제약, 완료 조건을 전달합니다.
- 실패 승격에는 문제, 관련 파일·구조, 증거, 시도와 결과, 현재·대안 가설, 필요한 판단을 추가합니다.
- 동일 실행자의 같은 원인에 대한 구현·수정은 최초 시도와 증거 기반 추가 수정 1회, 총 2회까지입니다. 이후 자동 재시도를 중단하고 책임자가 새 근거·가설·검증 계획으로 재진단하여 추가 실행 여부를 결정합니다. 모델 교체만으로 횟수를 초기화하지 않습니다. 책임자가 이미 실행 중이면 자체 재진단 또는 독립 자문을 수행합니다. 구조적 위험·요구사항 모순·데이터 무결성 위험은 즉시 책임자에게 전달합니다.
- 도구·권한·환경 장애와 모델 추론 실패를 구분합니다. 모델을 바꾸는 것만으로 환경 문제를 해결하려 하지 않습니다.
- 진단한 책임자가 바로 수정하는 편이 효율적이면 재위임하지 않습니다.
- 기본은 메인과 작업자 1개이며, 독립 작업의 실익이 있을 때만 병렬 실행합니다. 실제 런타임 제한을 따릅니다.
- 공통 계약과 파일 소유권을 먼저 정하고 다른 작업자의 변경을 되돌리지 않습니다. 불필요한 중첩 위임과 전체 저장소 재탐색을 줄입니다.
- 완료는 실제 검증 결과와 요구사항 충족으로 판단합니다. 입력 수락, 작업 시작, 실행 중, 검토 대기, 완료를 구분합니다.
- 모델 이름·역할 이름·요청한 인수만으로 실제 모델 전환을 주장하지 않습니다.

인증·인가, 암호화, 운영 인프라, 파괴적 데이터 작업과 데이터 손실 위험이 있는 마이그레이션은 전문 분석·검토를 먼저 거칩니다. 대상, 복구 방법과 데이터 무결성 확인 방법을 확정하고, 실패 영향이 매우 크면 독립 검토를 추가합니다. 설치 승인을 운영 배포나 권한 우회, 추가 유료 크레딧 사용의 승인으로 취급하지 않습니다.

### 장시간 실행 프로세스와 로그

2026-11-04 로컬 백엔드 bootRun 출력과 Gradle 데몬 로그가 각각 70GB 넘게 쌓여 디스크가 96% 찬 사례에서 나온 공통 규칙입니다. 어떤 프로젝트·도구에서든 적용하며 Codex·Claude Code 전역 지침과 Paseo 프로젝트 정책(POLICY E, Orca 병행기 보관본 포함)에 포함됩니다.

- 서버·watch의 표준출력을 크기 제한 없는 파일에 통째로 받지 않고, 크기 제한이 있는 앱 로그 파일에 남깁니다. 출력 파일을 쓸 때는 크기를 주기적으로 확인합니다.
- Gradle로 서버를 띄울 때(`bootRun` 등)는 `--no-daemon`을 붙입니다. 데몬 로그(`~/.gradle/daemon/<버전>/daemon-*.out.log`)는 콘솔 출력을 크기 제한 없이 복사하고 서버를 멈춰도 14일 뒤에야 정리됩니다.
- SQL 결과 전체를 찍는 로그(log4jdbc `jdbc.resultsettable` 등)는 켜지 않고, 필요할 때만 잠깐 켜서 크기 제한이 있는 파일에만 남깁니다. 콘솔에는 info 이상만 보냅니다.
- 로그에는 업무 데이터·개인정보가 들어갈 수 있으므로 작업이 끝나면 직접 띄운 서버를 멈추고 임시 로그를 정리합니다. 남겨야 하면 로컬 작업 기록 폴더에만 둡니다.
- 작업을 마치거나 보고할 때 직접 띄운 백그라운드 프로세스와 그 로그 크기를 함께 보고합니다.

## 모델 라우팅

**Paseo(와 병행기 Orca)에서는 Terra·Luna·Sonnet을 역할과 유형에 맞춰 배정합니다.** Paseo 오케스트레이터(Root·Coordinator)는 Paseo 도구가 있는 Claude Sonnet high만 쓰고 대체 후보가 없습니다. Opus·Sol은 승격 조건이나 고위험 작업에서만, Fable·Astra는 Opus·Sol로도 해결하지 못한 최종 단계에서만 사용합니다. 라우터는 필수 품질 기준을 먼저 충족한 경로의 전체 비용을 비교합니다. 평가 기준은 토큰 수가 적은 모델이 아니라 **작업을 성공적으로 끝내는 데 든 총비용**입니다.

모델 ID·작업 유형·승격 순서·재시도 상한·대체 모델은 [`policy/model-routing.json`](policy/model-routing.json) 한 곳에서 관리합니다. Codex의 Luna·Sol·Astra와 프로젝트 전용 Terra 선택은 실행할 때마다 30일 이내에 갱신된 `CODEX_HOME/models_cache.json`에서 해당 계열의 최신 표시 가능·API 지원 모델을 찾아 사용합니다. 설정의 `id`는 캐시가 없거나 오래됐거나 계열 일치 모델이 없을 때 쓰는 마지막 확인 ID입니다. 캐시는 읽기만 하며 자동 갱신하지 않습니다. Claude 모델은 현재 명시된 버전을 고정해서 사용합니다.

라우팅 결과의 `model_resolution`이 `codex_catalog`이면 현재 Codex 모델 캐시에서 세대를 선택한 것입니다. `pinned_fallback`이면 캐시가 없거나 30일보다 오래됐거나 일치 항목이 없어 설정의 마지막 확인 ID를 사용한 것이므로 최신 세대라고 간주하지 말고, Codex가 모델 캐시를 갱신한 뒤 라우팅을 다시 확인합니다.

| 복잡도 | 대상 예시 | Paseo·Orca Worker | Claude 단독 | Codex 단독 |
| --- | --- | --- | --- | --- |
| 역할: 루트 오케스트레이터·프로젝트 코디네이터 | 작업 분해·조정·최종 검토 | Paseo: Sonnet high / Sonnet high (Orca: Terra high / Luna high) | Sonnet medium | Luna high |
| LEVEL 1 단순 | 이름 변경, 문서, 테스트 작성, 정형 코드, 단순 UI, 기존 패턴 반복, 일반 코드 분석 | Luna medium | Sonnet low | Luna medium |
| LEVEL 2 일반 | 기능·API·데이터 로직·프론트엔드, 일반 버그 | Luna high | Sonnet medium | Luna high |
| LEVEL 3 복잡 | 다중 모듈, 상태 관리, 성능, 비동기, 통합, 복잡한 데이터 흐름 | Sonnet high | Sonnet high | Luna xhigh |
| LEVEL 4 고난도 | 중대한 구조 변경, 동시성, 반복 미해결 오류, 광범위 분석, 보안, 데이터 무결성 | Opus high 또는 Sol high | Opus high | Sol high |
| LEVEL 5 최종 단계 | LEVEL 4에서도 2회 실패한 문제만 (시작 레벨로 쓰지 않음) | Fable high 또는 Astra high | Fable high | Astra high |

파일·심볼 조회와 정형 추출은 Haiku 4.5(Claude) 또는 Luna medium(Codex)이 맡습니다. Claude 단독 세션에서 Luna를 쓰려고 Codex를 호출하지 않습니다. 도구 간 전달 비용이 절약분보다 크기 때문입니다.

**승격.** 같은 실행자가 검증 실패·원인 미파악·복잡도 급증으로 2회 실패하면 한 단계 승격합니다(Orca의 교차 진단은 역할별 라우팅 참고). 구조 위험·요구사항 모순·데이터 무결성 위험은 즉시 LEVEL 4로 갑니다. 환경·권한·외부 서비스·테스트 환경·모델 접근 오류는 승격 사유가 아니며 같은 모델로 상태를 보존한 채 원인을 해결합니다. 모델을 바꿔도 시도 횟수는 초기화되지 않습니다. LEVEL 4(Opus/Sol)에서도 2회 실패하면 최종 단계인 LEVEL 5(Fable/Astra)로 올리고, 거기서도 2회 실패하면 자동 승격을 멈추고 사용자에게 증거와 필요한 판단을 넘깁니다. 고위험 작업이나 대체 모델 선택으로 LEVEL 5에 바로 가지 않습니다.

**승격 인계.** 전체 대화를 넘기지 않고 목표, 관련 파일, 현재 구현 상태, 오류, 시도 내용, 실패 가설, 필요한 판단만 구조화해 전달합니다. 상위 모델은 문제 분석이나 핵심 결정만 맡고, 구현은 가능하면 Sonnet·Luna가 이어받습니다. 해결되면 후속 작업은 원래 복잡도의 기본 모델로 돌아갑니다.

**고위험 작업.** 인증·인가, 암호화, 운영 인프라, 파괴적 DB 작업, 데이터 손실 위험이 있는 마이그레이션, 데이터 무결성은 승격을 기다리지 않고 처음부터 LEVEL 4 분석·검토와 Human Gate를 거칩니다. 비용 절약은 이 안전 규칙보다 우선하지 않습니다.

**토큰 절약 원칙.** 작업과 직접 관련된 파일·문서·설정만 전달하고 이미 확보한 분석은 재사용합니다. 독립 실행·검증이 가능한 단위로 나누되, 나누는 비용이 더 크면 하나로 둡니다. 같은 목표의 에이전트를 중복 생성하지 않고, 전체 저장소 탐색과 같은 파일의 반복 분석을 피하며, 끝난 에이전트는 바로 종료하고 중간 보고는 짧게 합니다. 병렬 실행은 독립 작업의 실익이 있을 때만 하며 동시 작업자는 3개, 동시 상위·최종 단계 모델(Opus·Sol·Fable·Astra 합계) 작업자는 1개 이하입니다.

### 라우팅·사용량 명령

```bash
# Paseo: 작업 유형 또는 복잡도로 모델 선택 (JSON에 create_agent 시작 구성 paseo_create_agent·paseo_profile 포함)
python3 -B -m ai_policy.routing --host paseo --task-type docs
python3 -B -m ai_policy.routing --host paseo --role project_coordinator
python3 -B -m ai_policy.routing --host paseo --task-type code_review_claude   # 리뷰 모드(paseo_review) 포함

# 병행기 Orca 호스트 (JSON에 orca worker-start 인수 포함, 1.5.0과 출력 동일)
python3 -B -m ai_policy.routing --host orca --task-type docs
python3 -B -m ai_policy.routing --host codex --task-type docs --model-catalog /path/to/models_cache.json
python3 -B -m ai_policy.routing --host orca --resolve-family terra --effort high  # 프로젝트가 선택한 계열과 effort 유지, 버전 ID만 최신화
python3 -B -m ai_policy.routing --host orca --task-type feature --failures 2 --failure-kind verification
python3 -B -m ai_policy.routing --host orca --task-type docs --resolved   # 해결 후 원래 작업 유형의 기본 모델로 복귀
python3 -B -m ai_policy.routing --host orca --task-type docs --available sonnet,opus   # 사용 불가 모델 대체

# 작업 결과 기록과 모델별 사용량·성공률 보고 (로그의 사용량 수치만 읽고 대화 내용은 읽지 않음)
python3 -B -m ai_policy.usage record --task-id T-1 --model <라우팅 결과의 model 값> --task-type docs --success true --verified true
python3 -B -m ai_policy.usage report --since 2026-11-01
```

라우팅 결과의 `action`은 `run`, `retry`, `escalate`, `retry_same_model_preserve_state`, `return_to_default`, `handoff_to_lead`, `blocked_no_available_model` 중 하나입니다. Orca 호스트의 `orca_worker_args`는 `run`·`retry`·`escalate`·`retry_same_model_preserve_state`·`return_to_default`일 때만 채워지며, Paseo 호스트는 `orca_worker_args`를 비우고 같은 조건에서 `paseo_create_agent`(`provider`는 `<tool>/<model>`, `settings.modeId`·`thinkingOptionId`·리뷰의 `features`)를 채웁니다. Paseo 프로필에는 매개변수가 없으므로 `paseo_profile`은 이름 안내일 뿐이며 Owner가 값을 `create_agent`에 복사합니다. 호출자는 실행 전에 `action`을 확인합니다. 사용할 수 있는 모델이 없으면 종료 코드 40(`blocked_no_available_model`), LEVEL 5까지 실패하면 종료 코드 41(`handoff_to_lead`)로 인수를 비우고 작업 상태를 보존합니다. LEVEL 5는 시작 레벨로 지정할 수 없고, 그 레벨의 실패를 보고할 때만 `--level 5 --failures N`으로 넘깁니다. 상위 모델은 대체 모델로도 선택되지 않습니다. 사용량 보고는 Claude Code 세션 로그와 Codex rollout 로그의 모델·토큰·캐시 수치만 집계합니다. 비용 단가는 출처가 확인될 때까지 설정에 넣지 않으며, 그동안 비용은 `not_collected`로, 추천은 성공 1건당 토큰으로 계산합니다.

## Codex 전략

**Luna가 메인과 구현을 맡고, Sol은 승격 조건에서만 진단을 맡는 비용 우선 전략**입니다. Luna를 반복 작업에만 제한하지 않고, 기존 패턴과 계약이 명확한 중간 규모 기능까지 맡깁니다.

| 책임 | 모델 | 초기 추론 수준 |
| --- | --- | --- |
| 메인·요구사항·통합·최종 검토 | Luna 계열 최신 캐시 모델 | `high` |
| 기능 구현·관련 검증 (LEVEL 2) | Luna 계열 최신 캐시 모델 | `high` |
| 단순 작업·좁은 탐색·정형 변환 (LEVEL 1) | Luna 계열 최신 캐시 모델 | `medium` |
| 복잡한 개발 (LEVEL 3) | Luna 계열 최신 캐시 모델 | `xhigh` |
| 승격·고위험 진단 (LEVEL 4) | Sol 계열 최신 캐시 모델 | `high` |
| 최종 단계 (LEVEL 5, Sol 2회 실패 후) | Astra 계열 최신 캐시 모델 | `high` |
| 선택적 독립 검토 | 사용 가능한 Claude 모델 | 실제 지원 수준 |

```text
Luna high 메인이 범위·공통 계약·완료 조건 정의
  → Luna 작업자 구현·검증
  → 메인이 diff·검증 근거·통합 동작 검토

같은 원인으로 2회 실패
  → 한 단계 승격 (Luna medium → high → xhigh → Sol high)

구조·무결성 위험, 요구사항 모순, 고위험 작업
  → 바로 Sol high가 진단 (가능하면 구현은 Luna로 복귀)

Sol도 2회 실패
  → 최종 단계 Astra high, 여기서도 실패하면 사용자 판단
```

Astra는 Sol까지 실패한 경우에만 쓰는 마지막 단계이며 일상 경로가 아닙니다. 작은 작업은 직접 완료하고, Sol이 진단 후 바로 수정하는 편이 싸면 다시 넘기지 않습니다.

이 배분의 근거는 Luna의 집중된 작업에 대한 효율성과 6.1 Sol의 복잡한 작업에 대한 역할입니다. 공식 Codex 문서는 Luna의 시작 추론 수준으로 high를 안내합니다. 역할별 담당 범위 확대는 프로젝트에서 평가할 운영 제안이며 Luna가 모든 작업에서 Sol과 같다는 주장은 아닙니다. [공식 모델 안내](https://learn.chatgpt.com/docs/models), [서브에이전트 안내](https://learn.chatgpt.com/docs/agent-configuration/subagents)

### Codex 적용 위치와 확인

전역 지침은 유효한 `CODEX_HOME`의 `AGENTS.md`, 모델 기본값은 같은 위치의 `config.toml`에 반영합니다. 기본 디렉터리는 `~/.codex`입니다.

기본 설정은 메인 Luna high, 서브에이전트 Luna high이며 단순 작업·조사에는 medium을 명시합니다. 2026-11-06 이전 설치본은 메인이 Sol medium(실제 설정은 Terra medium)이었습니다. 환경이 지원하면 동시 서브에이전트 상한을 3개로 설정합니다. `AGENTS.override.md`, 프로젝트 지침과 사용자 지정 에이전트 설정이 적용을 바꿀 수 있으므로 확인합니다.

파일 수정과 새 세션의 유효 설정 확인은 구분합니다. 현재 메인 모델은 정책 문구만으로 바뀌지 않습니다. [전역 지침 로딩](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

## Claude Code 전략

**Sonnet이 메인과 구현을 맡고, Opus는 승격 조건과 고위험 작업에서만 쓰는 비용 우선 전략**입니다. Haiku는 단순 조회, Fable은 Opus까지 실패한 문제의 최종 단계에 한정합니다.

| 책임 | 기준 모델 ID | 초기 추론 수준 |
| --- | --- | --- |
| 메인·요구사항·통합·최종 검토 | `claude-sonnet-5-5` | `medium` |
| 단순 작업 (LEVEL 1) | `claude-sonnet-5-5` | `low` |
| 일반 기능 구현·관련 검증 (LEVEL 2) | `claude-sonnet-5-5` | `medium` |
| 복잡한 개발·재현 버그·정밀 검증 (LEVEL 3) | `claude-sonnet-5-5` | `high` |
| 파일 탐색·정형 추출·짧은 요약 | `claude-haiku-5-5` | effort 지정 안 함 |
| 승격·고위험 진단 (LEVEL 4) | `claude-opus-5-5` | `high`, 필요 시 `xhigh` |
| 최종 단계 (LEVEL 5, Opus 2회 실패 후) | `claude-fable-5-1` | `high` (2026-11-06 접근 확인) |
| 선택적 독립 검토 | 사용 가능한 Codex 모델 | 실제 지원 수준 |

```text
Sonnet medium 메인이 범위·공통 계약·완료 조건 정의
  → Sonnet low/medium/high 작업자 구현·검증 (복잡도에 따라)
  → 메인이 diff·검증 근거·통합 동작 검토

같은 원인으로 2회 실패
  → 한 단계 승격 (Sonnet low → medium → high → Opus high)

구조·무결성 위험, 요구사항 모순, 고위험 작업
  → 바로 Opus high가 진단 (가능하면 구현은 Sonnet으로 복귀)

Opus도 2회 실패
  → 최종 단계 Fable high, 여기서도 실패하면 사용자 판단
```

Opus는 진단한 문제를 직접 수정하는 편이 더 싸면 완료까지 맡습니다. 해결 뒤 후속 작업은 Sonnet으로 돌아갑니다. Fable은 출시 순서나 이름만으로 모든 작업에서 우월하다고 가정하지 않으며, Opus까지 실패한 문제에만 쓰는 마지막 단계입니다. 최종 단계에서는 진단과 수정을 함께 맡깁니다(fable-specialist).

### Claude 모델 근거와 기존 전략의 변경

2026-10-07 공식 목록에서 확인한 운영 후보는 Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 4.5입니다. 확인 환경은 Claude Code 2.1.290이었으며, 최소 읽기 전용 호출에서 sonnet과 opus가 각각 `claude-sonnet-5-5`, `claude-opus-5-5`로 응답했습니다. Fable·Haiku는 이 확인 과정에서 실제 호출하지 않았습니다. 이 결과는 해당 환경의 접근 확인이며 구현 성능 평가가 아닙니다. [공식 모델 목록](https://platform.claude.com/docs/en/models/overview)

제품 기본 추론 수준은 Opus 5.5·Sonnet 5.5 모두 medium이지만, 이 정책의 운영값은 Sonnet을 레벨에 따라 low·medium·high로, Opus는 승격 전용이므로 high로 둡니다. API 문서의 기본 추론값을 Claude Code 설정에 그대로 대입하지 않으며 별칭의 제공자별 해석을 확인합니다. [Claude Code 모델 설정](https://code.claude.com/docs/en/model-config)

단순 작업의 강제 인계와 모호한 재시도 횟수를 없애고, 자문과 실행의 권한을 분리합니다. Codex의 Terra 등 고정 계층 대신 실제 사용 가능한 모델을 확인해 독립 검토를 배정합니다.

### Claude 적용 위치와 에이전트

사용자 지침은 `~/.claude/CLAUDE.md`, 설정은 `~/.claude/settings.json`, 개인 에이전트는 `~/.claude/agents/`에 반영합니다. 실제 설정 디렉터리를 먼저 확인하고 개인 지침의 관리 영역만 갱신합니다.

권장 에이전트는 sonnet-light(low), sonnet-engineer(medium), sonnet-debugger(high), haiku-worker, opus-lead(high 자문), opus-specialist(high 실행), fable-specialist(high, 최종 단계 진단·실행)입니다. 자문은 Read·Grep·Glob만 허용하고 Bash·Edit·Write나 쓰기 MCP 권한을 허용하지 않습니다. 실행자는 승인된 수정·검증에 필요한 도구만 사용합니다. [커스텀 서브에이전트](https://code.claude.com/docs/en/sub-agents)

모델은 지원되는 model 설정, 추론은 현재 버전의 모델별 설정으로 저장합니다. 최상위 effortLevel만으로 최신 모델에 적용된다고 가정하지 않습니다. 조직 정책, 환경 변수와 프로젝트 설정이 이를 덮어쓸 수 있으며 기존 세션 재개·safe/bare 모드는 일반 새 세션과 다를 수 있습니다. CLAUDE.md는 행동 지침이며 모델·권한을 강제하는 설정은 아닙니다. Agent Teams·Ultracode는 설치 과정에서 자동 활성화하지 않습니다. [지침 로딩](https://code.claude.com/docs/en/memory), [설정 우선순위](https://code.claude.com/docs/en/settings)

## Paseo 전략

**Gitflow 기준 아래의 작업 워크스페이스(worktree)에서 업무를 실행하고, Codex·Claude 모델을 하나의 후보군으로 선택하는 프로젝트별 전략**입니다(초안, 2026-11-25). 기존 전역 지침은 유지하며 Paseo 업무에 더 구체적인 실행·모델 배정 정책을 적용합니다. 공통 본문은 [`policy/paseo-common.md`](policy/paseo-common.md), 절차는 [Paseo agent lifecycle](docs/paseo-agent-lifecycle.md), 모델 매핑은 [Paseo 모델 라우팅](docs/paseo-model-routing.md), Orca와의 대응·결정·미확인 목록은 [이전 설계](docs/paseo-migration-design.md), 프로젝트 설치는 [Paseo 설치 지시서](paseo-project-setup.md)입니다.

### Gitflow 기준과 작업 위치

| 유형과 이름 | 분기 기준 | 반영 대상 |
| --- | --- | --- |
| `feature/<업무명>` | 통합 `dev`/`develop` | 통합 브랜치 |
| `release/<버전>` | 통합 `dev`/`develop` | 운영 + 통합 브랜치 |
| `hotfix/<버전>` | 운영 `main`/`master` | 운영 + 통합 브랜치 |

이후 새 작업부터 위 Gitflow 관례를 적용합니다. 기존 `dev`는 develop 역할을 유지하고 자동으로 이름을 바꾸지 않으며, 진행 중인 업무의 브랜치·워크스페이스·에이전트명도 유지합니다. 프로젝트의 실제 통합·운영 브랜치 매핑을 먼저 확인하고, 병합·버전 태그·배포는 업무의 승인 범위 안에서 진행합니다.

- 새 업무는 `create_workspace`(`isolation: worktree`, `mode: branch-off`, 명시한 `baseBranch`, Gitflow `branchName`)로 만든 새 워크스페이스에서, 같은 업무의 후속 작업은 기존 워크스페이스에서 합니다. 생성 전에 기준 ref를 SHA로 확정하고 생성 후 초기 HEAD·실제 경로·브랜치·워크스페이스 ID·프로젝트 ID를 확인합니다.
- Git 기준(ref·SHA), Paseo 프로젝트 소속, 에이전트의 부모(`paseo.parent-agent-id`)는 서로 다른 사실이므로 각각 확인합니다. Orca의 parent workspace와 `--no-parent` 규칙은 Paseo에 대응이 없어 폐기했고, 그 목적(기능 브랜치에서 재분기 금지)은 `baseBranch` 명시와 HEAD 확인으로 유지합니다.
- 기능 브랜치에서 요청해도 새 업무는 유형별 기준 브랜치에서 분기합니다. 통합·운영 기본 체크아웃과 `isolation: local` 워크스페이스에서 일반 업무를 수정하지 않습니다. 기준을 확인할 수 없으면 중단하고 다른 브랜치로 자동 대체하지 않습니다.
- 선택한 기준의 로컬·원격 차이를 확인하고 기준을 기록합니다. 강제 reset·checkout이나 미커밋 변경 정리로 조건을 맞추지 않습니다.
- 여러 저장소 업무는 저장소별 워크스페이스·기준 SHA를 기록하고 하나의 업무 TASK_ID로 연결합니다. Paseo agentId·workspaceId는 업무 TASK_ID와 구분해 로컬 실행 기록에 매핑합니다.
- `archive_workspace`는 worktree 삭제로 취급하며 사용자 승인 사항입니다.

### 역할과 도구 구분 없는 모델 배정

Root(프로필 `root-orchestrator`)는 사용자 의도와 최종 판단·동시 실행 한도, Coordinator(`project-coordinator`)는 작업 위치·모델 선택·Worker 생성·회수·정산, Worker는 실제 조사·구현·문서·검증을 맡습니다. 각 Task 실행 단위의 Owner는 부모 에이전트 하나이며, Worker는 재위임하지 않습니다(정책 규칙 + Owner의 자식 목록 점검). Codex는 Paseo 도구가 없어 Worker로만 쓰고 Paseo worktree에서 commit하지 않습니다(diff 보고 후 Claude Worker 또는 Owner가 commit). 단일 프로젝트·단일 Worker·짧고 동기적인 저위험 목표는 Root가 Coordinator를 겸할 수 있고, 복수 프로젝트·병렬·장기·고위험 조율에는 Coordinator를 둡니다.

| 역할 | 기본 | 대체 후보 |
| --- | --- | --- |
| Root / Coordinator | Sonnet high / Sonnet high | 없음(Paseo 도구가 있는 Claude만) |
| 좁은 탐색·추출 | Luna medium | Haiku |
| LEVEL 1 단순 작업·문서·테스트 | Luna medium | Sonnet 5.5 |
| LEVEL 2 일반 개발 | Luna high | Sonnet high |
| LEVEL 3 복잡한 개발 | Sonnet 5.5 high | Terra high |
| LEVEL 4 승격·고위험 | Opus 5.5 high 또는 Sol 6.1 high | 서로 대체 |
| LEVEL 5 최종 단계 (LEVEL 4 2회 실패 후) | Fable 5.1 high | Astra high |

세부 유형은 [Orca 작업 유형별 모델 라우팅](docs/orca-model-routing.md)의 표를 Paseo도 그대로 씁니다(`orca_task_routes` 공유). Owner는 `python3 -B -m ai_policy.routing --host paseo ...` 결과의 `action`을 확인한 뒤 `paseo_create_agent`와 `paseo_profile`로 `create_agent`를 만듭니다. 결과의 요청값과 실제 실행값(확인 방법은 미확인)을 따로 기록합니다. 리뷰어는 구현자와 다른 도구 또는 독립 컨텍스트로 하며, Claude 리뷰어는 `plan` 모드, Codex 리뷰어는 `plan_mode`를 권장하되 **읽기 전용이 강제된다고 주장하지 않고** 리뷰 전후 `git status`·diff 무변경 검사를 필수 증거로 합니다. 쓰기 차단이 필요한 중요 리뷰는 Claude `plan` 모드 리뷰어를 씁니다.

### 생명주기와 신뢰성

완료 알림은 «턴이 끝났다»는 신호이지 업무 완료가 아닙니다. 수락 응답은 시작의 증거가 아니며 `running` 상태 또는 활동 기록으로 확인합니다. 대기는 알림 기반으로 하고 폴링하지 않습니다. 결과와 검증 근거를 확보하고 Worker가 `running`이 아님을 확인한 뒤 `archive_agent`로 정리하고 정리 상태를 기록합니다. 보고 형식은 Paseo 데몬이 모든 에이전트에 주입하는 `PROJECT_DONE:`/`BLOCKED:`/`NEED_APPROVAL:` 접두어 프로토콜을 그대로 쓰며 정책 고유 항목(요구·완료·검증 근거, 원장, 정산)을 그 메시지에 추가합니다. Owner 원장은 Task 로컬 기록 폴더에 둡니다. 데몬 재시작·Owner 장애 대응과 세션 시작 환경 점검은 [lifecycle 문서](docs/paseo-agent-lifecycle.md)를 따릅니다.

### 권한과 Human Gate

기본 권한 모드에서 Claude `bypassPermissions`와 Codex `full-access`를 쓰지 않습니다. 설치 요청·에이전트 생성·권한 요청 승인은 운영 실행·배포·통합 브랜치 병합·worktree 삭제의 포괄 승인이 아닙니다. Paseo 특유의 다음 행위는 Human Gate로 사용자 결정을 받습니다: relay 사용 여부(현재 켜져 있으며 사용자가 의도한 설정으로 확인됨, 임의로 바꾸지 않음), 비밀번호·CORS 변경, 플러그인 설치, schedule 생성, 권한 모드 상향, `archive_workspace`. 라우팅을 성립시키려고 도구·권한·Paseo 설정을 넓히지 않습니다.

### 설치 산출물은 Git 추적 금지

Paseo와 프로젝트 Task 정책을 설치·갱신하면서 생성한 로컬 설정·지침·검사기·템플릿·snapshot·설치 기록은 **Git add·commit·push 대상에서 제외**합니다. 이 저장소의 원본 설치 지시서와 실제 업무 코드·설계·납품 문서·공유 Task README는 별도로 관리합니다.

| 로컬 설치 산출물 | 포함 예시 |
| --- | --- |
| 에이전트 진입·설정 | 생성된 AGENTS.md·CLAUDE.md, 도구별 로컬 설정·hook |
| 설치 정책·템플릿 | 생성된 PASEO_POLICY·MODEL_ROUTING·WORKTREE_RULES·TASK_POLICY·ARTIFACTS·SESSION_START, Task 템플릿 |
| 설치 검사·사본 | scripts/ai-policy의 설치 guard·adapter·검사 파일, .ai-agent-policy snapshot·SHA256SUMS |
| 설치·실행 기록 | INSTALLATION.md·GENERATED.md, context·manifest·로그·백업 |

설치 manifest에 실제 생성 경로를 기록하고 저장소 로컬 `info/exclude` 또는 기존 `.gitignore`에 정확한 경로만 등록합니다. `docs/`·`scripts/` 전체를 제외하지 않습니다. `git ls-files`로 비추적, `git check-ignore -v --no-index`로 제외 규칙, staging diff로 설치 파일 미포함을 확인합니다. 이미 추적된 파일은 ignore만 추가해도 계속 추적되므로, 순수 설치 산출물은 대상과 백업을 확정한 마이그레이션에서 `git rm --cached -- <정확한 경로>`로 추적만 해제하고 로컬 파일을 보존합니다. 기존 공유 지침과 설치 블록이 섞인 파일은 자동으로 전체 untrack하지 않습니다.

### 설치와 실행 차단

정책 준비 검사는 생성 전 Gitflow 유형·기준·모델 접근과 업무 ID·문서 위치·예정 브랜치 확인, 생성 후 실제 워크스페이스·브랜치 확인, setup 성공 확인, **정책 준비 검사**(진입 지침·manifest 해시·guard·hook 로딩 대조), Task 등록·매핑 확정, Worker 시작 확인으로 나눕니다. 워크스페이스 생성, 정책 파일 설치, 클라이언트 신뢰, hook 로딩은 서로 다른 상태이며 `paseo.json` setup 성공만으로 준비 완료로 보지 않습니다. 최초 설치·정책 복구는 설치 전용 Worker가 통합 기준 워크스페이스에서 제한된 범위로 수행합니다.

지침만으로 모든 경로의 강제를 보장하지 않습니다. 문서 적용, 시작 경로 검사, 도구별 수정 차단을 구분하고 지원되지 않는 경로를 보고합니다. guard의 Paseo 모드는 (1) setup 훅으로 정책 설치 자동화 → (2) 새 세션에서 hook 실제 로딩 확인 → (3) 그 뒤에만 켜며, 구현 전 설계와 구현 후 변경을 LEVEL 4가 검토합니다(이 저장소에는 아직 구현이 없습니다). Paseo 경유 세션에서 프로젝트 hook이 실행되는지와 Codex 세션의 AGENTS.md 로딩은 미확인이며 첫 사용에서 확인합니다. 작업공간이 분리돼도 DB·포트·외부 시스템은 별도로 충돌을 확인합니다.

### Orca 병행기와 보관

기존 Orca 정책 파일(`orca-project-setup.md`, `docs/orca-model-routing.md`, `docs/orca-worker-lifecycle.md`, `docs/reproducible-orca-environment.md`, `policy/orca-common.md`, `--host orca`)은 삭제하지 않고 맨 위에 «보관(병행기)» 표시를 두며 동작은 그대로입니다. 병행기에는 기존 Orca가 소유한 진행 중 Run·worktree만 Orca 규칙으로 마무리하고, 이를 Paseo로 옮기거나 새 Run을 Orca에 추가하지 않습니다. 모든 Orca Run이 정산되고 Dispatch가 release 처리되면(Task 연결표·로컬 기록의 Run 목록을 `orca orchestration run-show`로 대조해 확인) «보관» 상태로 확정합니다. 이 확인 전에는 Orca 규칙을 폐기하지 않습니다. 전역 Orca hook·statusLine·theme 정리는 그 이후 사용자 승인으로 진행합니다. Orca 정책 본문의 설치·감지(`ai_policy` 번들 `policy/bundle.json`)와 Paseo 번들(`policy/paseo-bundle.json`)은 서로 다른 설치 경로·마커를 쓰므로 함께 설치해도 충돌하지 않습니다.

## 프로젝트 Task·문서·브랜치 전략

**실제 AI 업무는 같은 Task ID로 요구사항·설계·계획·실행·리뷰·검증·커밋을 연결하고, 기록과 실제 브랜치가 일치해야 시작·완료할 수 있습니다.** 작업자는 문서 관리를 선택 사항으로 취급하거나 다른 모델·스킬을 이유로 생략하지 않습니다. 단순 질문·조회만 하는 대화는 새 폴더를 만들지 않으며 실제 변경·공유 산출물 업무로 전환되기 전에 등록합니다.

기존 지침 생성 키트에서 문서 저장소·Task 분해·루트 진입 연결 방식을 확인했고, 적용된 산출물 정책에서 업무 ID별 정본, 로컬 초안·증거 분리, 세션 시작 확인과 관련 저장소·브랜치 기록 방식을 확인했습니다. 이 설치 정책은 그 구조를 일반화하고 **Task와 실제 브랜치의 필수 연결, 문서 커밋과 완료 게이트**를 추가합니다. 특정 프로젝트의 도메인 문서·경로·관례를 다른 프로젝트에 복사하지 않습니다.

### 그룹과 단일 프로젝트의 문서 위치

| 구조 | 공유 정본 | 로컬 전용 |
| --- | --- | --- |
| 프로젝트 그룹 | 확인한 문서 Git 저장소의 기존 업무 경로 또는 `docs/tasks/<TASK_ID>/` | 접근 가능한 업무 작업공간의 `.local-artifacts/tasks/<TASK_ID>/` |
| 단일 Git 프로젝트 | 같은 저장소의 기존 업무 경로 또는 `docs/tasks/<TASK_ID>/` | 해당 작업공간의 `.local-artifacts/tasks/<TASK_ID>/` |

그룹의 문서 저장소가 불명확하면 임의 저장소를 선택하거나 조용히 단일 방식으로 바꾸지 않습니다. 기존 도메인 원본·납품 문서·ADR·도구 상태 파일은 유지하고 Task 색인에서 연결합니다. 초안·원시 로그·추출물은 로컬에 두고 정제한 팀 공유 문서만 커밋합니다.

### Task ID와 브랜치 추적

기존 업무 ID를 재사용하고 신규 기본값은 `YYYY-MM-DD-<목적-slug>`입니다. 이후 새 업무는 기존 Gitflow 관례대로 `feature/<업무명>`, `release/<버전>`, `hotfix/<버전>`을 사용합니다. 일반 수정·문서 업무도 feature이며 운영 긴급 수정만 hotfix입니다. Task ID는 별도로 유지하고 저장소별 실제 브랜치를 연결표로 추적합니다.

```text
TASK_ID: 2026-10-07-example-feature

문서 저장소  → feature/example-feature
backend      → feature/example-feature
frontend     → feature/example-feature

공유 기록: 문서 저장소/docs/tasks/2026-10-07-example-feature/README.md
```

Task README와 공용 색인은 배정 시 담당자를 지정합니다. 비담당 Worker는 변경·검증·커밋 요약을 전달하고 담당자만 공유 기록을 갱신·커밋합니다. Paseo에서는 Owner(부모 에이전트)가 결과를 회수해 문서 담당 Worker에게 전달하며(병행기 Orca는 Controller), 수신과 실제 반영·커밋을 구분합니다. Codex Worker는 Paseo worktree에서 commit하지 못하므로 문서 담당은 가능하면 Claude Worker로 배정합니다. 단독 정책에서는 현재 Agent가 문서 담당자일 수 있습니다.

Task README에는 목적·요구 출처·완료 조건·담당·수정 범위와 저장소별 실제 브랜치, 생성 기준 ref/SHA, 소유 범위, 확인한 커밋·PR을 기록합니다. 문서 저장소도 수정 대상 행으로 포함합니다. 개인 worktree 경로·Paseo agentId·workspaceId(병행기 Orca workspace/터미널 ID)는 로컬 실행 기록에 두고 공유 문서는 저장소·브랜치·업무 ID로 찾을 수 있게 합니다.

업무 TASK_ID와 Paseo agentId·workspaceId(병행기 Orca Task/Run/Dispatch ID)는 별개이며 연결표로 대응합니다. 기존 브랜치와 legacy mapping은 보존합니다. 새 표준 Gitflow 이름에 Task ID가 없는 것은 정상 연결표로 추적하며 legacy 예외로 취급하지 않습니다. 신규 업무의 규칙을 맞추기 위해 기존 작업을 강제 rename하지 않습니다.

### 생략할 수 없는 시작·완료 조건

- 시작 전 정책 원문, Task 기록, 문서 정본, 실제 저장소·브랜치와 수정 범위를 확인합니다. 필수 기록·매핑이 없거나 원본에 접근할 수 없으면 의존 업무를 시작하지 않습니다.
- 범위·담당·모델·검증이 바뀌면 해당 체크포인트에서 기록을 갱신하고 인계 시 같은 업무 ID를 전달합니다. 브랜치·워크트리 전환은 현재 매핑 유지·예정 기록 → 업무 중지 → 전환·실제 checkout 확인 → 매핑 확정 후 재개 순서입니다. 실패하면 실제 상태로 매핑을 복구하고 차단 상태를 기록합니다. 전환 중에는 기록된 예정 대상에 대한 비강제 브랜치·작업공간 전환과 확인·매핑 확정·복구를 허용합니다. 구현·검증과 위치 검사 우회는 허용하지 않습니다.
- 완료 전 검증 결과와 제한, 관련 저장소의 변경·커밋, 공유 문서 갱신·커밋 상태를 확인합니다. 문서 커밋 외 완료 조건을 충족하면 최종 커밋용 완료 상태를 작업본에 준비하되 해당 문서 커밋 성공 시 확정 조건을 표시합니다. 커밋 성공·필요 변경 포함을 확인한 뒤에만 외부에 전체 완료를 보고하고 완료 게이트를 통과합니다. 실패하면 커밋 대기로 기록하며 문서 커밋이나 검증이 보류됐으면 전체 완료로 보고하지 않습니다.
- 관련 문서의 로컬 커밋은 기본 업무 계약으로 설치하되 기존 저장소의 더 엄격한 승인·서명·훅 규칙을 보존합니다. 담당 파일만 stage하고 커밋 메시지 또는 trailer에 업무 ID를 기록합니다.
- 코드 커밋·원격 푸시·병합·배포는 해당 업무의 승인 범위를 따릅니다. 문서의 로컬 커밋과 팀 원격 공유 완료는 구분합니다.
- 여러 저장소는 원자적으로 커밋되지 않습니다. 일부 성공은 부분 완료로 기록합니다. 문서의 자기참조 커밋 SHA를 만들지 않고 최종 문서 SHA는 Git 이력과 최종 보고로 추적합니다.

정책 문구뿐 아니라 지원되는 프로젝트 시작·도구 실행·완료 검사에도 이 조건을 연결합니다. Task 없음, 미기록 브랜치 전환과 미커밋 문서의 완료 보고를 거부하도록 설계합니다. 지원되지 않는 경로는 실행 차단 미검증으로 보고하며 모든 환경에서 절대 우회 불가능하다고 주장하지 않습니다.

### 설치와 다른 정책 연동

설치 지시서는 TASK_POLICY·ARTIFACTS·SESSION_START와 Task README 템플릿을 기존 원본과 충돌 없이 연결합니다. 진입 파일의 `project-task-policy:begin/end` 블록만 관리하고 기존 Orca·Paseo·모델 지침과 프로젝트 보정을 보존합니다.

Paseo 정책이 있으면 업무 유형별 Gitflow 기준 워크스페이스 검사는 Paseo 정책이 맡고, 이 정책은 Task 등록·브랜치 연결·업무 정본·문서 커밋을 맡습니다. 없으면 확인한 현재 프로젝트의 브랜치 규칙으로 문서 관리만 수행합니다. 단독 설치에 Paseo나 Codex·Claude 양쪽 CLI를 요구하지 않습니다. 병행기 동안 기존 Orca 업무에는 Orca 연동 문구(project-task-policy-setup.md의 Orca 결합 항목)가 그대로 유효합니다.

그룹의 설치 정책은 확인한 로컬 정본과 버전이 고정된 미추적 사본·검증된 로컬 스냅샷으로 연결합니다. 실제 업무 Task 정본을 각 코드 저장소에 중복 복제하지 않습니다. 다른 컴퓨터·새 워크트리에는 설치 manifest의 버전·해시를 대조해 로컬 진입 파일과 정책을 재설치하고 실제 로딩을 검증합니다. 설치 파일을 기준 커밋에 넣어 전파하지 않습니다.

## 업데이트와 효과 검증

업데이트할 때 GitHub 변경 이력을 확인하고 해당 설치 파일을 다시 적용합니다. 기존 파일을 백업하고 관리 영역만 갱신하며 개인 지침, 관련 없는 설정과 프로젝트 보정은 보존합니다. 세션 시작 때마다 원격 파일을 다운로드하거나 실행하지 않습니다.

`python3 -B -m ai_policy.usage report`로 모델별 토큰·캐시 사용량과 작업 유형별 성공률·재시도·승격 횟수를 모읍니다. 대표 업무 10~15개로 첫 실행 성공률, 최종 정확성, 완료 시간, 모든 에이전트의 전체 사용량, 메인의 재작업, 승격 횟수와 통합 결함을 비교합니다. 이 저장소를 작성하면서 구현 벤치마크를 수행한 것은 아닙니다. 후보 모델의 성능 향상이 실제 업무 절약으로 이어지는지는 이 평가로 판단합니다.
