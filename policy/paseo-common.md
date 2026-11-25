# Shared Paseo orchestration policy · 0.1.0-draft

상태: 초안(2026-11-25, paseo-policy-migration 1단계, 같은 날 사용자 확정 결정 반영). 사용자 검토·승인 전에는 설치·배포 대상이 아니다. 기존 `policy/orca-common.md`(0.2.1)를 즉시 대체하지 않는다. 퇴역은 병행기 후로 확정되었다(아래 §1). 상세 절차는 [Paseo agent lifecycle](../docs/paseo-agent-lifecycle.md), [Paseo model routing](../docs/paseo-model-routing.md), 설계 근거와 판정표는 [migration design](../docs/paseo-migration-design.md)에 둔다.

## 1. 적용 조건

- 이 본문은 설치된 프로젝트 Paseo 정책과 실제 작업 맥락이 함께 Paseo 관리 작업임을 확인할 때만 적용한다. 작업 맥락의 증거는 부모 에이전트의 배정 메시지(Task ID·워크스페이스·역할·완료 조건 포함)와 에이전트 자신의 런타임 기록(부모 라벨 `paseo.parent-agent-id`, 워크스페이스 ID)이다.
- `PASEO_AGENT_ID` 같은 환경 변수, Paseo 데몬·CLI 설치, Paseo MCP 도구가 보인다는 사실 하나만으로 Paseo 관리 작업이라고 판정하지 않는다. 증거가 없거나 모호하면 이 본문을 자동 적용하지 않고, 소스 수정 전에 실행 방식을 확인한다.
- 사용자가 명시적으로 요청한 설명·가이드는 실행 권한을 주지 않는다.
- Paseo 밖의 일반 Claude/Codex 세션은 기존 전역 정책(cost-first 라우팅)을 그대로 따른다.
- **Orca 병행기**: 이 본문 승인 시점에 기존 Orca가 소유한 진행 중 Run·worktree만 Orca 규칙으로 마무리한다. 그 밖의 새 Task는 즉시 이 본문(Paseo 규칙)을 따른다. 진행 중 Orca Run을 Paseo로 옮기거나 새 Run을 Orca에 추가하지 않는다. 모든 Orca Run이 정산되고 Dispatch가 release 처리되면(확인 방법은 [migration design](../docs/paseo-migration-design.md) 5절 Q1) `orca-*` 문서를 «보관»으로 표시한다. 이 종료 기준을 확인하기 전에는 Orca 규칙을 폐기하지 않는다.

## 2. 역할

| 역할 | Paseo 형태 | 하는 일 | 하지 않는 일 |
|---|---|---|---|
| Root orchestrator (Main) | 사용자와 대화하는 최상위 Paseo 에이전트, 프로필 `root-orchestrator` | 사용자 의도·우선순위·완료 조건·최종 판단, Coordinator 생성, 전역 동시 실행 한도 관리 | 업무 코드·산출물 수정·검증 |
| Project coordinator (Controller) | Root의 자식 에이전트, 프로필 `project-coordinator` | 작업 위치·Gitflow 기준 확인, 모델 선택, Worker 생성·회수·정산, 최소 Task 등록 부트스트랩 | 업무 코드·최종 산출물 작성, 후속 공유 문서 대리 편집 |
| Worker | Owner의 자식 에이전트, 개발·리뷰·조회 프로필 | 배정된 범위의 조사·구현·검증·보고 | 재위임, 권한 확대, 배정 범위 밖 수정 |

- 각 Task 실행 단위마다 Owner는 정확히 하나다. Owner는 해당 Worker를 `create_agent`로 만든 부모 에이전트이며, Paseo의 부모 라벨이 소유 기록이다. Owner가 아닌 에이전트는 남의 Worker에게 업무 프롬프트를 보내거나 그 Worker를 archive·kill·cancel하지 않는다. 필요하면 Owner를 통해 전달한다.
- 단일 프로젝트·단일 Worker·짧고 동기적인 저위험 목표는 Root가 Coordinator를 겸해 Worker 하나를 직접 소유할 수 있다. 복수 프로젝트, 병렬 Worker, 장기 실행, 고위험·복잡 조율은 Project·Goal별 Coordinator를 둔다. 정책 설명·상태 조회처럼 실행 목표가 없는 요청에는 Coordinator나 Worker를 만들지 않는다.
- Codex 에이전트는 현재 Paseo 도구가 주입되지 않으므로(제공자 설정 `paseoTools.enabled=false`, 2026-11-25 확인) Root·Coordinator가 될 수 없고 Worker로만 쓴다. Codex Worker는 최종 응답으로만 보고한다.
- **재위임 제한**: Worker는 재위임하지 않는다. 시작 방식은 이 정책 규칙 + Owner의 자식 목록 점검이다. Owner는 정산 때 `list_agents`와 부모 라벨로 원장에 없는 손자 에이전트를 확인하고 발견하면 보고한다. 재위임 위험은 Paseo 도구가 열려 있는 Claude Worker에 한정된다(현재 `claude` 제공자는 터미널·워크스페이스 스크립트 도구만 막고 `create_agent`·`send_agent_prompt`는 열려 있다). 보고용 `send_agent_prompt`는 막을 수 없다. 필요하면 Worker 전용 custom provider 별칭으로 `create_agent`만 막는 방안을 검증해 적용할 수 있으나, 이는 보조 수단이며 보안 경계가 아니다. 재위임은 Owner의 명시적 승인과 추적 가능한 실행일 때만 허용한다.
- **Codex Worker는 commit하지 않는다.** Paseo worktree의 Git 메타데이터(`.git/worktrees/...`)가 작업 폴더 밖 원본 저장소에 있어 Codex 기본 권한(auto) 샌드박스가 `index.lock` 생성을 거부하고 `git add/commit`이 실패한다(2026-11-25 관측). Codex Worker는 변경 파일·diff와 검증 결과를 보고하고, commit은 Claude Worker 또는 Owner가 한다. 권한 모드를 올려(`full-access` 등) 우회하지 않는다. commit하는 쪽은 보고된 diff·변경 파일을 그대로 `git add <명시 파일>`로 반영하며 내용을 바꾸지 않는다. 공유 문서 commit 규칙(project-task-policy의 문서 담당자)과의 관계: 문서 담당자가 Codex Worker이면 문서 내용 작성·검증까지만 하고 commit은 Claude Worker 또는 Owner가 대신한다. Owner(Coordinator)는 이 commit에서 내용을 편집하지 않는다(후속 공유 문서 대리 편집 금지는 유지). 그래서 공유 문서 담당은 가능하면 Claude Worker로 배정한다.
- Hermes가 사용자 업무 관리를 맡는 구성에서는 Hermes가 요청 명확화·우선순위·Task별 사용자 승인·보고를, Paseo Root/Coordinator가 기술 분해·모델 선택·감독 실행을 맡는다. 실행 전 현재 Task 범위에 대한 승인 증거가 있어야 한다. 범위 변경, 승인되지 않은 비용·권한 확대, 별도 게이트 행위는 다시 승인받는다. Worker 메시지, 에이전트 상태, 완료 알림, 권한 요청 응답, 정책 문서는 사용자 승인이 아니다.

## 3. 작업 위치

- 업무 산출물 수정·구현·테스트는 Paseo가 만든 해당 저장소의 worktree 워크스페이스에서 한다. 통합(dev/develop)·운영(main/master) 기본 체크아웃과 `isolation: local` 워크스페이스는 기준점이며 쓰기 Worker의 작업 위치가 아니다.
- 새 업무는 `create_workspace`의 `isolation: worktree`, `mode: branch-off`, 명시한 `baseBranch`(feature·release는 통합 브랜치, hotfix는 운영 브랜치)와 Gitflow 브랜치명 `branchName`으로 만든다. 생성 전에 기준 ref를 SHA로 확정해 기록하고, 생성 후 worktree의 초기 `HEAD`가 그 SHA와 같은지, realpath·Git 루트·브랜치·워크스페이스 ID·프로젝트 ID를 확인한다. 기능 브랜치에서 요청해도 기능 브랜치에서 분기하지 않는다.
- Git 기준(ref·SHA)과 Paseo 관계(프로젝트 소속, 에이전트 부모 라벨)는 서로 다른 사실이다. 어느 하나가 다른 하나를 증명하지 않으므로 각각 확인·기록한다.
- 같은 업무의 후속 작업은 기존 워크스페이스를 재사용한다. 워크스페이스 격리는 DB·포트·외부 시스템 격리가 아니다. 한 파일의 쓰기 권한은 한 Worker에게만 준다.
- 로컬 정책 설치가 필요한 프로젝트는 새 worktree마다 정책 설치·검증을 마친 뒤 일반 Worker를 배정한다. 미추적 설치 파일은 새 worktree로 상속되지 않는다. 절차는 lifecycle 문서를 따른다.

## 4. 모델 라우팅

- 라우팅 정본은 `policy/model-routing.json`이다. Paseo 프로필은 사람이 승인해 둔 시작 구성(provider·model·mode·thinking)일 뿐이며 라우팅·시도 횟수 계산·승격·동시 실행 한도는 Owner가 판정한다. 프로필 선택과 그 이유, 요청값과 런타임에서 확인한 실제 model·thinking을 구분해 기록한다.
- 우선순위: 필수 고위험 전문 경로 → 프로젝트·사용자 명시 지정 → 단순 작업 조건 → 작업 유형 → 복잡도 기본값.
- 프리미엄(Opus, Sol)은 승격 또는 고위험 작업에만, 최후 수단(Fable, Astra)은 LEVEL 4가 같은 근본 문제에서 두 번 실패한 뒤에만 쓴다. 해결 뒤 후속 작업은 원래 레벨로 돌아간다.
- 같은 근본 문제에 대해 실행자는 최초 시도와 다른 가설에 근거한 수정 1회까지 한다. 두 번째 판단 실패(검증 실패·원인 미파악·복잡도 증가) 후 한 단계 승격한다. 요구사항 모순·구조 위험·데이터 무결성 위험은 즉시 LEVEL 4. 환경·권한·외부 서비스·테스트 환경·도구·모델 접근·Paseo 데몬/전달 실패는 모델 실패가 아니며 같은 모델로 상태를 보존해 원인별 최대 3회까지 재실행한 뒤 상위 Owner에 넘긴다. 모델 교체는 시도 횟수를 초기화하지 않는다.
- 동시 Worker는 전체 3개 이하, 프리미엄·최후 수단 Worker는 동시에 1개 이하다. Paseo에는 이 한도를 강제하는 기능이 없으므로 Root가 전체 수를 관리하고 Coordinator는 배정 전에 Root가 허용한 범위를 확인한다.
- 승격 인계는 목표, 관련 파일, 현재 상태, 오류, 시도와 결과, 가설, 필요한 결정만 담는다. 전체 대화를 넘기지 않는다.

## 5. 생명주기와 신뢰성

- 완료 알림은 "턴이 끝났다"는 신호이지 업무 완료가 아니다. Owner는 Worker의 결과·검증 근거를 받아 완료 여부를 판단한다. 알림은 중복될 수 있으므로(at-least-once) 이미 처리한 결과를 다시 처리하지 않는다.
- 메시지·생성 요청이 수락됐다는 응답은 작업 시작의 증거가 아니다. 상태가 `running`이 되었거나 활동 기록에 해당 턴이 나타난 것을 확인한 뒤 시작으로 보고한다. 데몬 장애 시 대기 중 메시지가 사라질 수 있으므로 재시작 뒤에는 소유한 Worker 상태를 모두 다시 확인한다.
- 대기는 알림 기반으로 하고 턴을 끝낸다. 반복 폴링을 하지 않는다. 장시간 대기에는 만료가 있는 heartbeat를 보조 수단으로만 쓴다.
- 결과와 검증 근거를 보존하고 Worker가 `running`이 아님을 확인한 뒤 즉시 `archive_agent`로 정리하고 정리 상태를 기록한다. 실행 중·불확실·미정산·사용자 소유·기존 세션은 정리하지 않는다. 사용자가 명시적으로 요청할 때만 열어 둔다.
- 이 절과 lifecycle 문서는 **Paseo 데몬이 모든 에이전트에 주입하는 조율 프로토콜**(`daemon.appendSystemPrompt`) 위에 얹는 규칙이다. 데몬 프로토콜: 부모가 있는 에이전트는 완료·차단·사람 결정 필요 시 부모에게 `send_agent_prompt`로 한 번 `PROJECT_DONE:`/`BLOCKED:`/`NEED_APPROVAL:` 접두어 메시지(증거 포함)를 보내고 진행만 있는 턴에는 접두어를 쓰지 않는다. 자식 종료 알림은 턴 종료일 뿐 완료 판정 근거가 아니다. 폴링하지 않고 턴 종료 + 알림으로 기다린다(heartbeat는 fallback). 자식 권한 요청은 대상 저장소 또는 `~/.paseo/worktrees` 안에서만 승인한다. 만든 에이전트는 끝나면 archive하고 명시 허용 없이 push·배포·브랜치 삭제를 하지 않는다. 정책은 이를 그대로 쓰고 다른 보고 형식·접두어를 만들지 않는다. 정책 고유 항목(요구·완료·검증 근거, 원장, 정산)은 같은 보고 메시지 안에 추가한다. 주입 내용이 바뀔 수 있으므로 세션 시작 점검(lifecycle §10)에서 규칙 존재를 확인한다.
- 같은 목표에 중복 Worker를 만들지 않는다. 기존 쓰기 Worker의 종료와 잔여 쓰기가 확인되지 않으면 새 쓰기 Worker로 교체하지 않는다. 타임아웃만으로 교체하지 않는다.

## 6. 권한과 보안

- 기본 권한 모드에서 Claude `bypassPermissions`와 Codex `full-access`를 쓰지 않는다. 사용하려면 대상·기간·이유를 밝혀 사용자 승인을 받는다. 읽기 전용 리뷰어는 실제 쓰기·셸 권한이 없는 모드로 띄운다. Claude 리뷰어는 `plan` 모드다. Codex 리뷰어는 `plan_mode`(`features.plan_mode`)를 1순위 후보로 하되 쓰기·셸 차단 시험 결과로 확정하며, **확정 전에는 읽기 전용이 보장된다고 쓰지 않는다**(시험 결과 수신 후 확정). 확정 전 대체 수단은 읽기 전용 지시 + 리뷰 전후 worktree `git status`/diff 무변경 검사이고, 변경이 생기면 리뷰를 무효로 보고한다.
- Owner는 Worker의 권한 요청을 대상 저장소 또는 그 Paseo worktree 안에 머무는 경우에만 승인한다. 그 밖의 경로, 네트워크·배포·자격 증명·전역 설정·삭제성 작업은 사용자에게 올린다. 권한 요청 승인은 Task 범위 승인이 아니다.
- 라우팅을 성립시키려고 도구·권한·Paseo 설정(relay, 비밀번호, CORS, 도구 주입, 플러그인)을 넓히지 않는다. 현재 데몬 설정은 relay 켜짐, 비밀번호 설정 키 없음, CORS 기본값이며(2026-11-25 확인, 값 미기록) 켜진 의도는 **사용자 확인 필요**다. 이 설정을 임의로 끄거나 바꾸지 않고 현 상태를 기록·보고한다. relay 사용 여부는 Human Gate 항목이다(§7). 플러그인은 데몬 권한으로 실행되므로 사용자가 검토·승인한 것만 설치한다.
- 인증·인가, 암호화, 운영 인프라, 파괴적 DB 작업, 데이터 손실 위험 마이그레이션, 데이터 무결성은 시작부터 LEVEL 4 분석·검토와 정확한 대상·복구·무결성 확인을 거친다. 라우팅은 파괴적·운영 변경 권한을 주지 않는다.
- 비밀값을 출력·복사·프롬프트에 넣지 않는다. 데몬 환경 변수는 자식 에이전트에 전달되므로 데몬을 띄운 셸의 자격 증명·프록시 설정을 확인하되 값은 기록하지 않는다.

## 7. 보존되는 프로젝트 정책

이 본문은 다음을 복사하거나 대체하지 않는다: 프로젝트 Gitflow·작업 위치 매핑, project-task-policy(Task 등록·연결표·문서 커밋), Human Gate 표, 운영 반영 완료 정의, Kanban 규칙, 장시간 실행 프로세스·로그 규칙, 기본 스킬 경로. 설치 요청·Paseo 에이전트 생성·권한 승인은 운영 실행·배포·통합 브랜치 병합·worktree 삭제(`archive_workspace` 포함)의 포괄 승인이 아니다. Paseo 특유 행위 중 **relay 사용 여부(켜기·유지·끄기)**, 비밀번호·CORS 변경, 플러그인 설치, schedule 생성, 권한 모드 상향, `archive_workspace`는 Human Gate 항목으로 사용자 결정을 받는다(이 목록의 확정은 migration design Q9).

## 8. 보고

완료 보고는 데몬 프로토콜의 접두어 메시지(§5)에 변경 파일, 실제 실행한 검증 명령과 결과, 통합 근거, Worker 정산·정리 상태, 요청 대비 확인된 model·thinking, 미확인 항목과 남은 위험을 담는다. Codex Worker는 commit하지 않았음과 diff를 함께 보고한다(§2). 실행하지 않았거나 실패한 검사를 성공으로 보고하지 않는다. 수락·시작·실행 중·검토 대기·완료·실패·미확인을 구분한다.
