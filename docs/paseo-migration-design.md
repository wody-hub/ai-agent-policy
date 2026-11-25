# Orca → Paseo 정책 이전 설계 (paseo-policy-migration 1단계)

작성 2026-11-25. 상태: 사용자 검토 대기 초안. 브랜치 `docs/paseo-policy-source`(base main @ 91a473a).

이번 단계 산출물(신규 파일만, 기존 orca-* 파일 미수정):

- [policy/paseo-common.md](../policy/paseo-common.md): 공통 정책 본문 0.1.0-draft
- [docs/paseo-agent-lifecycle.md](paseo-agent-lifecycle.md): Orca Worker lifecycle 대응 규칙
- [docs/paseo-model-routing.md](paseo-model-routing.md): 프로필 매핑과 라우팅 책임, `model-routing.json` 변경 제안
- 이 문서: 개념 대응, MUST-PRESERVE 판정, 충돌 처리, 열린 질문, 후속 영향 파일

입력: `.local-artifacts/paseo-migration/evidence/paseo-technical-research.md`(Paseo v0.17.4 조사, 미설치 상태 조사), `custom-features-and-policies.md`(6절 MUST-PRESERVE 22개, 7절 C1~C15), 이 worktree의 orca 정책 파일, 원본 체크아웃의 미커밋 `docs/orca-worker-lifecycle.md`·`orca-project-setup.md`(worktree readiness 절, 읽기만 함), 2026-11-25 이 세션의 Paseo `list_profiles` 결과와 MCP 도구 스키마.

## 1. 설계 결정 요약

1. **소유 = 부모 관계.** Orca의 Run owner·Run 바인딩은 Paseo의 부모 라벨(`paseo.parent-agent-id`)로 대체한다. 완료 알림이 부모에게만 가므로 "Owner는 하나"가 런타임 구조와 일치한다. 재바인딩 기능이 없으므로 Owner 장애 시 "같은 Owner 재개 → 불가하면 새 Owner가 원장·상태로 정산" 절차를 둔다.
2. **알림은 신호, 정산은 Owner 판단.** `notifyOnFinish`는 at-least-once·턴 식별 없음·크래시 유실 가능이다. Owner는 원장으로 중복을 거르고, 수락과 시작을 구분하고, 재시작 후 전수 상태 확인을 한다.
3. **release = 정산 후 `archive_agent`.** archive가 실행 중 턴을 끊고 부모 archive가 자식까지 archive하므로 순서(정산 → archive)를 엄격히 한다. `archive_workspace`는 worktree 삭제로 취급한다.
4. **worktree = `create_workspace` branch-off + 명시 baseBranch + 초기 HEAD 확인.** Orca의 parent workspace 개념은 Paseo에 없으므로 폐기하고, Git 기준·Paseo 프로젝트·에이전트 부모를 각각 확인한다.
5. **프로필 = 시작 구성, 라우팅 = Owner.** `model-routing.json`이 정본이다. 오케스트레이터는 Paseo 도구가 있는 Claude만 가능하다(Codex는 Worker 전용).
6. **신뢰성·환경 점검을 정책 절차로 고정.** 데몬 재시작 대응, 로그인·프록시 환경 변수 전파, 한국어 locale, 권한 모드 금지 기본값.
7. **의미 불변 영역.** Human Gate, Task 정책 결합, 검증·완료 정의, 비밀 취급, Kanban, 로그 규칙은 문구만 Paseo 용어로 바꾸고 의미를 바꾸지 않는다.

## 2. Orca → Paseo 개념 대응표

| Orca 개념 | Paseo 대응 | 판정 | 근거·비고 |
|---|---|---|---|
| Main | Root orchestrator 에이전트(프로필 `root-orchestrator`, Claude Sonnet high) | 변경 | Codex 오케스트레이터 불가(사용자 승인 2026-11-25) |
| Controller | Root의 자식 Coordinator(프로필 `project-coordinator`) | 변경 | 역할 경계는 동일 |
| Managed Worker | Owner의 자식 에이전트(dev/review/lookup 프로필) | 변경 | Codex Worker는 최종 응답으로만 보고 |
| Run | Owner가 관리하는 Task 실행 단위 + 로컬 원장 | 변경 | Paseo에 Run 객체 없음 |
| Run owner | Worker의 부모 에이전트 | 변경 | `paseo.parent-agent-id` [DOC] |
| `run-create` | 없음(Owner 원장 생성) | 폐기 | |
| Dispatch | 한 Worker에 대한 배정 프롬프트와 그 턴 | 변경 | 턴 ID가 알림에 없음 → 원장 번호로 식별 |
| `worker-start --agent --model --effort` | `create_agent`(`provider`, `settings.modeId`, `settings.thinkingOptionId`, `workspaceId`, `title`, `labels`) | 변경 | [MCP] 프로필 매개변수 없음 |
| `orca_worker_args`(라우터) | 라우터 결과를 프로필/`create_agent` 필드로 수동 대응 | 변경 | `--host paseo`는 제안 P1 |
| worker accepted vs `turn_started` | 생성 응답 vs `running` 상태·활동 기록 | 유지 | 의미 동일 |
| `check --run --wait --timeout-ms` | `notifyOnFinish` 알림 + 단건 `get_agent_status` + 만료 있는 heartbeat | 변경 | MCP 대기 도구 없음 [DOC] |
| `worker_done` / settled failure | 알림 + 결과 보고 확보 + `running` 아님 확인 = 정산 | 변경 | 알림 ≠ 완료 |
| `worker-release --dispatch` | `archive_agent` | 변경 | 실행 중이면 중단됨 [MCP] |
| released / release_pending / release_unknown | archived / archive_pending / archive_unknown | 변경 | |
| keep-open 예외 | 동일(사용자 명시 요청 시만) | 유지 | |
| `consumer_fenced` | 대상 없음. 단일 Owner 규칙 + 고아 Worker 정산 절차 | 폐기 | 재바인딩 기능 없음 |
| `run-use` / `run-current` | 대상 없음. `detach`는 CLI·SDK 수동 기능 | 폐기 | [DOC lifecycle "Relationships"] |
| `run-show`, `inbox --terminal run:` | `get_agent_status`, `get_agent_activity`, `list_agents` + 원장 | 변경 | `list_agents`에 라벨 필터 없음 [MCP] |
| `--takeover-legacy` | 대상 없음 | 폐기 | |
| Orca mail wake → Main이 Controller에 전달 | 알림은 부모에게만 → 전달 불필요 | 변경 | |
| `worktree create --repo --base-branch --parent-worktree` | `create_workspace`(`isolation: worktree`, `mode: branch-off`, `baseBranch`, `branchName`, `projectId`, `path`) | 변경 | [MCP] |
| Orca parent workspace(기준 워크스페이스 자식) | 없음. Paseo 프로젝트 소속만 | 폐기 | 원칙 "Git base와 parent는 별개"는 "Git 기준 / Paseo 프로젝트 / 부모 에이전트를 각각 확인"으로 재정의 |
| `--no-parent` 금지 | 대상 없음 | 폐기 | 목적은 baseBranch 명시·HEAD 확인으로 유지 |
| 초기 HEAD == 기준 SHA | 동일 | 유지 | |
| realpath·Git 루트·브랜치·workspace ID 확인 | 동일 + Paseo projectId | 유지 | |
| 카드·Worker 표시 이름 = 브랜치명 | `create_workspace.title`·`create_agent.title`(60자 제한) | 변경 | 60자 초과 시 원장에 원명 |
| `setup=run`, wait-for-setup | `paseo.json` setup 훅 | 변경 | setup 성공 ≠ 정책 준비 |
| worktree readiness before dispatch | 동일 개념 이월 | 유지 | lifecycle 4.2절 |
| Orca 컨텍스트 감지(`ai_policy.context`, ORCA_* 환경 변수, orca CLI 조회) | 부모 배정 메시지 + 부모 라벨 + 설치된 프로젝트 정책 | 변경 | `PASEO_AGENT_ID` 단독은 증거 아님. 자동 감지 구현은 후속 |
| Orca 실행 재시도 3회 | Paseo 비모델 실패 재시도 3회 | 유지 | 분류에 Paseo 특유 실패 추가 |
| Orca agent hook·statusLine·theme(C11) | 없음 | 후속 | 3단계에서 사용자 승인 후 정리 |
| Orca Task(내부) ↔ 업무 TASK_ID 매핑 | Paseo agentId·workspaceId ↔ 업무 TASK_ID | 변경 | Task 연결표 열 이름 변경 필요 |
| 동시 Worker 3 / 프리미엄 1 | Root가 계수(Paseo 상한 없음 [SRC]) | 변경 | |
| 읽기 전용 리뷰어(Read/Grep/Glob) | Claude `plan` 모드 / Codex는 지시만 | 변경 | 열린 질문 Q3 |
| Hermes ↔ Orca Coordinator 역할 분담 | Hermes ↔ Paseo Root/Coordinator | 유지 | 명칭만 |

## 3. MUST-PRESERVE 22개 판정

판정: 유지 = 의미·요구 그대로(명칭만 바뀔 수 있음), 변경 = 의미는 지키되 이행 방법이 바뀜, 폐기 = 요구 자체를 없앰.

| # | 정책 | 판정 | Paseo에서의 형태 / 사유 | 위치 |
|---|---|---|---|---|
| 1 | Main/Controller 코드 미수정, Worker 실행, 재위임 금지, 단일 Owner, 소규모 겸임 예외 | 변경 | Owner=부모 에이전트. Codex는 Worker 전용. 재위임 차단은 정책+보조 설정(보안 경계 아님) | common §2 |
| 2 | 설치 정책+실제 작업 맥락이 있을 때만 적용, 환경 변수·CLI만으로 판정 금지 | 변경 | 증거 종류를 Paseo 배정 메시지·부모 라벨로 교체. 원칙 동일 | common §1 |
| 3 | Hermes 역할 분담·승인 증거·재승인·메시지≠승인 | 유지 | Orca Coordinator → Paseo Root/Coordinator. 권한 요청 승인·완료 알림도 사용자 승인이 아님을 추가 | common §2 |
| 4 | 비용 우선·검증 생략 금지, 기본/프리미엄/최후 수단, 정본 json, 실제 모델은 런타임 증거로 | 변경 | 프로필 계층 추가. 오케스트레이터 기본 Sonnet high(Codex 제외). 실제 모델 확인 경로 [미확인] | routing §1–3 |
| 5 | 승격 2회, 비모델 3회, 즉시 L4, 구조화 인계, 기본 복귀 | 유지 | Owner 원장으로 계산. Paseo 특유 비모델 실패 분류 추가 | routing §4 |
| 6 | 동시 3 / 프리미엄 1, 관련 파일만, 중복 금지, 끝난 에이전트 정리 | 변경 | 런타임 상한 없음 → Root 계수. 정리는 `archive_agent` | routing §4, lifecycle §5–6 |
| 7 | 목표/범위/완료 조건 재진술, 인계 필수 항목, 질문 ≤3, 충돌 먼저 보고 | 유지 | 배정 계약에 포함 | lifecycle §2.3 |
| 8 | 실작업 전 Task 등록·브랜치 매핑, 동일 Task ID | 유지 | 연결표의 Orca Task/Run/Dispatch 열을 agentId·workspaceId로 교체(2단계) | §6 |
| 9 | 실제 검증 근거로 완료 판단, 상태 구분, 실패를 성공으로 보고 금지 | 유지 | 알림≠완료 규칙으로 강화 | common §5, §8 |
| 10 | 독립 리뷰, 리뷰 경로, 읽기 전용 리뷰어, 고위험 전문 검토 | 변경 | Claude 리뷰어 `plan` 모드. Codex 리뷰어 읽기 전용 강제 수단 미확인(Q3) | routing §2 |
| 11 | 새 업무=기준 브랜치 아래 새 관리 worktree, 기준 SHA, 위치 확인, 기본 체크아웃 금지, `--no-parent` 금지, 단일 쓰기, 격리≠DB/포트 격리 | 변경 | `create_workspace` branch-off. parent 개념·`--no-parent` 규칙 폐기(대상 없음), 목적은 유지 | common §3, lifecycle §4.1 |
| 12 | worktree별 정책 설치 후 배정, 비추적 설치 산출물 | 유지 | `paseo.json` setup ≠ 준비 완료 추가 | lifecycle §4.2 |
| 13 | 병합·태그·푸시·배포는 승인 범위 내, 설치 요청≠승인, release/hotfix 양쪽 반영 | 유지 | `archive_workspace`를 worktree 삭제로 명시 | common §7, lifecycle §5.8 |
| 14 | 운영 반영 완료 정의 | 유지 | 변경 없음 | common §7 |
| 15 | 범위 지정 대기, 정산 후 release, release 상태 기록, 활성·불확실·사용자 소유 정리 금지, consumer_fenced 재바인딩 | 변경 | 알림 기반 대기·`archive_agent`. `consumer_fenced`·`run-use`는 폐기하고 Owner 장애 절차로 대체 | lifecycle §3, §5, §8 |
| 16 | 고위험은 처음부터 Opus/Sol high 분석·검토, 라우팅≠권한 | 유지 | | common §6 |
| 17 | Human Gate 표 | 유지 | 표 자체는 프로젝트 문서 그대로. Paseo 특유 게이트 행위 추가 제안(§5 Q 참고) | common §7 |
| 18 | 권한 확대 금지, 유료 크레딧 자동 승인 금지 | 유지 | `bypassPermissions`/`full-access` 기본 금지, 권한 요청 승인 범위 규정 추가 | common §6 |
| 19 | 비밀 취급 | 유지 | 데몬 환경 변수 전파 주의 추가(값 미기록) | common §6, lifecycle §10 |
| 20 | 장시간 프로세스·로그 규칙 | 유지 | 배정 계약·보고 형식에 포함 | lifecycle §2.3, §7 |
| 21 | Kanban 규칙 | 유지 | 변경 없음. 한글 locale(#3513) 위험 점검 추가 | lifecycle §10 |
| 22 | 기본 스킬 경로 표 | 변경 | "구현 조율" 행의 "Orca 작업이면 orca-orchestrator"를 Paseo 작업용 경로로 교체 필요(3단계, 대상 스킬 결정은 Q6) | §6 |

합계: **유지 14, 변경 8, 폐기 0.** 하위 요소 중 폐기: `run-create`, `consumer_fenced`, `run-use`/`run-current`, `--takeover-legacy`, Orca parent workspace, `--no-parent` 금지 규칙(모두 Paseo에 대상이 없음).

## 4. 충돌 C1~C15 처리

| # | 내용 | 처리 | 사유·후속 |
|---|---|---|---|
| C1 | Sonnet effort: 전역 문서 medium vs settings.json high | 보류 | 전역 Claude 설정 단계(3단계)에서 결정. Paseo 오케스트레이터 high는 프로필로 별도 관리되므로 이 초안과 충돌하지 않음 |
| C2 | 버전 드리프트(전역 1.4.0, 라우팅 1.5.0, GH v1.0.4/1.0.5) | 반영(부분) | Paseo 본문은 별도 버전 0.1.0-draft. GH 재설치는 2단계 |
| C3 | GH MODEL_ROUTING(v1.0.4)이 1.5.0과 다름 | 보류 | "프로젝트 명시 지정 우선" 규칙 때문에 GH 구버전 값이 이긴다. 2단계에서 GH 문서를 Paseo 기준으로 재생성해야 함(Q7) |
| C4 | Hermes coordinator Sol medium, Hermes 기본 Opus minimal | 보류 | Hermes 설정은 범위 밖. Hermes 계속 사용 여부 확인 필요(Q8) |
| C5 | Kanban 마크다운 vs Hermes Kanban | 보류 | Paseo 이전과 무관. 기존 정책 유지 |
| C6 | 볼트 Orca README 낡음 | 보류 | 3단계 영향 목록에 포함 |
| C7 | Codex/Claude 전역 문서 병렬 사본 | 반영(설계) | 3단계에서 두 전역 문서의 Paseo 단락을 이 저장소 한 원본에서 생성하도록 제안 |
| C8 | ai-guideline-kit 중복 사본 | 보류 | 범위 밖 |
| C9 | haman "구현은 Codex, 리뷰는 다른 Agent" 고정 | 반영 | Paseo 정책도 두 계열 모두 구현·리뷰 허용(단 오케스트레이션은 Claude). haman 로컬 문서는 수정하지 않음 |
| C10 | Orca의 `.orca/AGENTS.md` 자동 로딩 가정 | 반영 | Paseo Claude는 SDK `settingSources`로 CLAUDE.md 등을 읽는다 [SRC]. Codex app-server의 AGENTS.md 로딩은 [미확인] → 준비 검사에서 새 세션 로딩 확인을 요구 |
| C11 | Orca hook·statusLine 전역 설치 | 보류 | Orca 퇴역 승인 후 3단계에서 정리. 이 초안은 전역 설정을 건드리지 않음 |
| C12 | Kanban tr:id 혼재 | 보류 | 무관 |
| C13 | 깨진 orcahq gateway, korean-law MCP | 보류 | 운영 정리 항목. 사용자 결정 |
| C14 | Task 정책 설치 편차 | 보류 | Paseo 정책도 Task 정책을 필수로 요구하지 않음(기존과 동일) |
| C15 | README "자동 설치 없음" vs `ai_policy.install` | 보류 | 단, 설치기·번들이 Orca 전용(`REQUIRED`에 `orca-common.md`, 설치 경로 `.config/ai-agent-policy/orca`)이므로 Paseo 번들 설계 시 함께 정리(3단계) |

## 5. 열린 질문 (사용자 결정 필요)

상위 5개(우선순위 순):

**Q1. Orca 정책 퇴역 시점**
- (a) 병행기: 진행 중인 Orca Task는 Orca 규칙으로 끝내고 새 Task부터 Paseo 규칙 적용, 모든 Orca Task 종료 후 orca-* 문서를 "보관"으로 표시 — **권장**
- (b) 즉시 일괄 교체
- (c) 무기한 병행
- 권장 사유: 진행 중 Run/Dispatch 정산 규칙이 사라지면 정리 상태가 불명확해진다.

**Q2. 프로젝트 실행 차단(guard.py)의 Paseo 모드**
- (a) guard에 Paseo 모드 추가: 작업 위치가 Paseo worktree 루트 아래인지, 브랜치·초기 기준 SHA·Task 연결표 일치, 기본 체크아웃 쓰기 거부를 Git 정보로 검사(Paseo 메타데이터 의존 최소화) — **권장**
- (b) 문서 규칙만 두고 guard는 Orca 모드 유지
- (c) guard 제거
- 권장 사유: 현재 7개 사본(gh-docs + 6개 저장소)의 Orca 모드는 Paseo 세션에서 통과 조건을 만들 수 없어 일반 작업이 막히거나 우회가 생긴다.

**Q3. Codex 리뷰어(`review-claude-work`)의 읽기 전용 보장**
- (a) Codex의 읽기 전용에 해당하는 모드가 있는지 먼저 확인해 프로필을 바꾸고, 확인 전까지는 지시 + 리뷰 전후 `git status`/diff 무변경 검사로 대체 — **권장**
- (b) Claude 구현 리뷰도 Claude `plan` 모드 리뷰어(독립 컨텍스트)로 바꿈(계열 교차 포기)
- (c) 현재 그대로(지시만)
- 권장 사유: MUST-PRESERVE 10의 "읽기 전용 리뷰어"를 지키면서 계열 교차 리뷰를 유지한다.

**Q4. Claude Worker의 Paseo 도구(재위임 수단) 제한**
- (a) 정책 규칙 + Owner의 자식 목록 점검(원장에 없는 손자 에이전트 발견 시 보고)으로 시작하고, 필요하면 Worker 전용 custom provider로 `paseoTools.disabledTools` 적용 — **권장**
- (b) 지금 바로 provider 단위로 `create_agent` 비활성화(같은 `claude` provider를 쓰는 Root·Coordinator도 막힐 수 있음)
- (c) 제한 없음
- 권장 사유: provider 단위 설정이라 오케스트레이터와 Worker를 같은 provider로 쓰면 함께 막힌다 [DOC mcp.md]. 별도 provider 구성은 검증이 필요하다.

**Q5. 데몬 운영 방식과 환경 전파**
- (a) 깨끗한 로그인 셸(UTF-8 locale)에서 CLI 데몬(`paseo daemon start`)을 띄워 앱 종료와 분리, `ANTHROPIC_BASE_URL`은 기존 전역 정책대로 유지 여부를 명시 결정 — **권장**
- (b) 데스크톱 앱 관리 데몬 + `keepRunningAfterQuit` 켜기(#3513 한글 위험 감수)
- (c) 현행 유지(확인 없음)
- 권장 사유: #3513(한글 깨짐), #3618(로그인 실패), 앱 종료 시 데몬 정지 위험을 한 번에 줄인다. 현재 데몬 실행 방식은 [미확인].

그 밖의 질문:

- Q6. 기본 스킬 경로 표의 Paseo 조율 스킬: `paseo` 스킬 사용 vs 이 정책 전용 신규 스킬. 권장: 기존 `paseo` 스킬 + 이 문서 참조.
- Q7. Coordinator Sonnet high를 `model-routing.json`에 반영(제안 P2)할지. 권장: 반영(사용자 승인 이미 있음).
- Q8. Hermes를 계속 사용자 업무 관리자로 쓸지. 쓰지 않으면 MUST-PRESERVE 3의 Hermes 문구를 조건부로 남긴다.
- Q9. Paseo 특유 행위의 Human Gate 추가 여부: relay 켜기, 플러그인 설치, `archive_workspace`, schedule 생성(비용 발생), 권한 모드 상향. 권장: 공통 게이트로 추가.
- Q10. Owner 원장 위치: Task 로컬 기록 폴더(`LOCAL_ARTIFACT_ROOT/<TASK_ID>/`) vs Paseo 라벨만. 권장: 로컬 기록(라벨 필터가 없음).

## 6. 후속 단계별 영향 파일

### 2단계: GH 프로젝트 (사용자 승인 후)

- `gh-docs/docs/guides/orca/ORCA_POLICY.md`, `MODEL_ROUTING.md`, `WORKTREE_RULES.md`, `INSTALLATION.md` → Paseo 판으로 재생성 또는 대체(위치·이름은 2단계 결정). Human Gate 표(ORCA_POLICY.md 38행~)는 의미 그대로 이전.
- `gh-docs/docs/guides/TASK_POLICY.md`: Orca Task/Run/Dispatch 참조를 Paseo agentId·workspaceId로, 연결표 열 이름.
- `scripts/ai-policy/guard.py`, `install.py`, `test_guard.py` 7개 사본: gh-docs, gh-rag-provider, New-Backend-RiskZero3, New-Batch-RiskZero3, New-Frontend-Riskzero3, New-Mobile-Backend-Riskzero, New-Mobile-Riskzero3(2026-11-25 `find` 확인). Orca 모드 → Paseo 모드(Q2).
- 6개 저장소 정책 스냅샷과 진입 파일(AGENTS.md/CLAUDE.md 관리 블록, v1.0.4/1.0.5), GH 공통 폴더 `AGENTS.md`·`CLAUDE.md`·`.orca/AGENTS.md`.

### 3단계: 이 저장소와 전역 설정 (사용자 승인 후)

- 이 저장소: `README.md`(Orca 전략 절), `orca-project-setup.md` → `paseo-project-setup.md` 신규, `project-task-policy-setup.md` POLICY F(Orca 결합 문구), `claude-code-global-model-routing-prompt.md`, `codex-global-model-routing-prompt.md`, `policy/model-routing.json`(제안 P1~P5), `policy/bundle.json`·`policy/adapters/*`, `ai_policy/bundle.py`(`REQUIRED`), `ai_policy/install.py`(설치 경로·마커가 orca 전용), `ai_policy/context.py`(ORCA_* 감지), `ai_policy/routing.py`(`--host paseo`), `tests/*`, `docs/reproducible-orca-environment.md`, 기존 `docs/orca-*.md`·`policy/orca-common.md`(보관 표시).
- 전역: `~/.claude/CLAUDE.md`("Confirmed Orca tasks" 절, 기본 경로 표 구현 조율 행, Runtime notes), `~/.codex/AGENTS.md`(Orca 단락), `~/.claude/settings.json`·`~/.codex/hooks.json`의 Orca hook·statusLine·theme(C11).
- 연관(정책 외, 영향만 기록): task-radar의 Orca 요청 outbox·relay-keeper, Hermes work-manager `policy.json`·orca-status 플러그인, `com.orcahq.gateway` launchd(C13), 볼트 `02_Projects/Orca/README.md`(C6), `~/.claude/skills`의 orca-* 스킬.

## 7. 미확인 목록

런타임 실행으로 검증하지 않았거나 조사 문서에 근거가 없는 항목이다.

1. `get_agent_status` 스냅샷에 실제 실행 model·thinking이 나오는지(요청값 대비 확인 경로).
2. `create_workspace.baseBranch`가 원격 ref(`origin/dev`)를 받는지, 로컬과 원격이 다를 때의 동작.
3. Paseo 경유 Claude 세션에서 프로젝트 hook(guard)이 실제 실행되는지, Codex app-server 세션이 AGENTS.md를 읽는지.
4. Codex에 읽기 전용(쓰기·셸 차단) 모드가 있는지(`auto-review`의 의미 포함).
5. Owner가 `closed` 상태일 때 완료 알림이 전달·재개되는지(#8464 관련).
6. 손자 에이전트 생성(중첩 오케스트레이션)의 실제 동작과 깊이 제한.
7. `labels` 키 규칙의 예약어 충돌 여부, `list_agents`의 라벨 조회 방법.
8. 에이전트별 토큰·비용을 MCP로 얻는 방법(SDK `lastUsage`만 문서화).
9. 현재 데몬 실행 방식(데스크톱 관리 vs CLI), locale, relay·비밀번호·CORS·도구 주입 설정 값.
10. 프로필 메모의 `gpt-6.2-sol`/`gpt-6.2-astra`와 json 고정 ID(`gpt-6.1-sol`/`gpt-6-astra`) 차이의 원인.
11. `#8436` 메시지 유실, `#7760` Codex 턴 후 정지가 v0.17.x에서 남아 있는지.
12. Claude Agent SDK 경유 구독 사용의 Anthropic 측 약관·과금 처리.
13. `paseo.json` setup 훅으로 정책 설치를 자동화할 수 있는지와 그 실패 시 동작.
