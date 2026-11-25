# Orca → Paseo 정책 이전 설계 (paseo-policy-migration 1단계)

작성 2026-11-25. 상태: 사용자 검토 대기 초안(2026-11-25 보정 반영, Q3 시험 결과 반영). 브랜치 `docs/paseo-policy-source`(base main @ 91a473a).

## 2026-11-25 보정 이력

1단계 초안(4a920ce)에 같은 날 사용자 확정 결정과 새로 확인된 사실을 반영했다. 기존 `orca-*` 파일, `model-routing.json`, GH 프로젝트, 전역 설정은 수정하지 않았다.

- **Q1~Q5 «결정됨»**(5절): Q1 병행기 후 퇴역(병행기 정의·종료 기준·확인 방법 명문화), Q2 guard Paseo 모드(순서 조건 3단계, 2단계 L4 검토 대상), Q4 정책 규칙 + Owner 자식 목록 점검(사실 보강), Q5 데몬 현 상태 명문화 + 시작 시 점검 항목. **Q3는 시험 결과로 «확정»**: Codex 리뷰어에 `plan_mode`를 권장하되 지침 수준 보호일 뿐 «강제된다»고 주장하지 않으며, 리뷰 전후 `git status`/diff 무변경 검사를 필수 증거로 한다. 쓰기 차단이 필요한 중요 리뷰는 Claude `plan` 모드 리뷰어. 프로필 변경은 제안 P6(사용자 승인 후).
- **F1 반영**: Paseo 데몬이 모든 에이전트에 주입하는 조율 규칙(`daemon.appendSystemPrompt`)을 «데몬이 이미 강제하는 기본 프로토콜»로 인용하고, 별도 보고 형식을 만들지 않으며 정책 고유 항목은 그 위에 얹는다(common §5, lifecycle §7).
- **F2 반영**: Codex 기본 권한(auto) 에이전트는 Paseo worktree에서 `git add/commit`이 샌드박스에 막힌다. «Codex Worker는 commit하지 않는다» 규칙과 문서 담당 commit 규칙 정리를 추가했다(common §3, lifecycle §5·§7). 7절 미확인 3·4번과 연결.
- **F3 반영**: `daemon.relay.enabled=true`, 비밀번호 계열 키 없음, CORS 기본값. 임의 변경 없이 «사용자 확인 필요»로 기록하고 relay 사용을 Human Gate(Q9)로 올렸다.
- **7절**: 확인된 항목을 «확인됨(일자·방법)»으로 옮기고 새 미확인을 추가했다.
- **변경 파일**: `policy/paseo-common.md`, `docs/paseo-agent-lifecycle.md`, `docs/paseo-model-routing.md`, 이 문서.

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
6. **신뢰성·환경 점검을 정책 절차로 고정.** 데몬 재시작 대응, 로그인·프록시 환경 변수 전파, 한국어 locale, 권한 모드 금지 기본값. 데몬 설정은 «바꾸기»가 아니라 «현 상태 명문화 + 시작 시 점검»(Q5).
7. **의미 불변 영역.** Human Gate, Task 정책 결합, 검증·완료 정의, 비밀 취급, Kanban, 로그 규칙은 문구만 Paseo 용어로 바꾸고 의미를 바꾸지 않는다.
8. **데몬 기본 프로토콜 위에 얹는다.** 데몬이 `daemon.appendSystemPrompt`로 이미 주입하는 보고 접두어(`PROJECT_DONE:`/`BLOCKED:`/`NEED_APPROVAL:`)·알림 해석·폴링 금지·권한 승인 범위·archive·push 금지 규칙을 정책이 인용하고, 충돌하는 별도 형식을 만들지 않는다. 정책 고유 항목(요구/완료/검증 근거, 원장, 정산)만 그 위에 추가한다.
9. **Codex Worker는 commit하지 않는다.** Paseo worktree의 Git 메타데이터가 작업 폴더 밖에 있어 Codex 기본 권한 샌드박스가 `index.lock` 생성을 거부한다. 변경 파일·diff를 보고하고 commit은 Claude Worker 또는 Owner가 하며, 권한 모드를 올려 우회하지 않는다.

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
| 읽기 전용 리뷰어(Read/Grep/Glob) | Claude `plan` 모드 / Codex는 `plan_mode` 권장(지침 수준, 강제 아님) + 리뷰 전후 무변경 검사 필수 | 변경 | Q3 확정(2026-11-25 시험), 프로필 변경은 P6 |
| 구현 Worker의 보고 형식 | 데몬 주입 프로토콜(`PROJECT_DONE:`/`BLOCKED:`/`NEED_APPROVAL:` + 증거) + 정책 고유 항목 | 변경 | F1. Codex Worker는 Paseo 도구가 없어 최종 응답으로 보고 |
| Worker의 commit(문서 담당 포함) | Claude Worker 또는 Owner. Codex Worker는 diff 보고만 | 변경 | F2 |
| Hermes ↔ Orca Coordinator 역할 분담 | Hermes ↔ Paseo Root/Coordinator | 유지 | 명칭만 |

## 3. MUST-PRESERVE 22개 판정

판정: 유지 = 의미·요구 그대로(명칭만 바뀔 수 있음), 변경 = 의미는 지키되 이행 방법이 바뀜, 폐기 = 요구 자체를 없앰.

| # | 정책 | 판정 | Paseo에서의 형태 / 사유 | 위치 |
|---|---|---|---|---|
| 1 | Main/Controller 코드 미수정, Worker 실행, 재위임 금지, 단일 Owner, 소규모 겸임 예외 | 변경 | Owner=부모 에이전트. Codex는 Worker 전용. 재위임 차단은 정책 규칙 + Owner의 자식 목록 점검(Q4). 재위임 위험은 Claude Worker에 한정(Codex는 Paseo 도구 없음). 보조 설정은 보안 경계 아님 | common §2 |
| 2 | 설치 정책+실제 작업 맥락이 있을 때만 적용, 환경 변수·CLI만으로 판정 금지 | 변경 | 증거 종류를 Paseo 배정 메시지·부모 라벨로 교체. 원칙 동일 | common §1 |
| 3 | Hermes 역할 분담·승인 증거·재승인·메시지≠승인 | 유지 | Orca Coordinator → Paseo Root/Coordinator. 권한 요청 승인·완료 알림도 사용자 승인이 아님을 추가 | common §2 |
| 4 | 비용 우선·검증 생략 금지, 기본/프리미엄/최후 수단, 정본 json, 실제 모델은 런타임 증거로 | 변경 | 프로필 계층 추가. 오케스트레이터 기본 Sonnet high(Codex 제외). 실제 모델 확인 경로 [미확인] | routing §1–3 |
| 5 | 승격 2회, 비모델 3회, 즉시 L4, 구조화 인계, 기본 복귀 | 유지 | Owner 원장으로 계산. Paseo 특유 비모델 실패 분류 추가 | routing §4 |
| 6 | 동시 3 / 프리미엄 1, 관련 파일만, 중복 금지, 끝난 에이전트 정리 | 변경 | 런타임 상한 없음 → Root 계수. 정리는 `archive_agent` | routing §4, lifecycle §5–6 |
| 7 | 목표/범위/완료 조건 재진술, 인계 필수 항목, 질문 ≤3, 충돌 먼저 보고 | 유지 | 배정 계약에 포함 | lifecycle §2.3 |
| 8 | 실작업 전 Task 등록·브랜치 매핑, 동일 Task ID | 유지 | 연결표의 Orca Task/Run/Dispatch 열을 agentId·workspaceId로 교체(2단계) | §6 |
| 9 | 실제 검증 근거로 완료 판단, 상태 구분, 실패를 성공으로 보고 금지 | 유지 | 알림≠완료 규칙으로 강화 | common §5, §8 |
| 10 | 독립 리뷰, 리뷰 경로, 읽기 전용 리뷰어, 고위험 전문 검토 | 변경 | Claude 리뷰어 `plan` 모드. Codex 리뷰어는 `plan_mode` 권장 + 무변경 검사 필수, 강제 주장 금지, 중요 리뷰는 Claude `plan`(Q3 확정) | routing §2 |
| 11 | 새 업무=기준 브랜치 아래 새 관리 worktree, 기준 SHA, 위치 확인, 기본 체크아웃 금지, `--no-parent` 금지, 단일 쓰기, 격리≠DB/포트 격리 | 변경 | `create_workspace` branch-off. parent 개념·`--no-parent` 규칙 폐기(대상 없음), 목적은 유지 | common §3, lifecycle §4.1 |
| 12 | worktree별 정책 설치 후 배정, 비추적 설치 산출물 | 유지 | `paseo.json` setup ≠ 준비 완료 추가 | lifecycle §4.2 |
| 13 | 병합·태그·푸시·배포는 승인 범위 내, 설치 요청≠승인, release/hotfix 양쪽 반영 | 유지 | `archive_workspace`를 worktree 삭제로 명시 | common §7, lifecycle §5.8 |
| 14 | 운영 반영 완료 정의 | 유지 | 변경 없음 | common §7 |
| 15 | 범위 지정 대기, 정산 후 release, release 상태 기록, 활성·불확실·사용자 소유 정리 금지, consumer_fenced 재바인딩 | 변경 | 알림 기반 대기·`archive_agent`. `consumer_fenced`·`run-use`는 폐기하고 Owner 장애 절차로 대체 | lifecycle §3, §5, §8 |
| 16 | 고위험은 처음부터 Opus/Sol high 분석·검토, 라우팅≠권한 | 유지 | | common §6 |
| 17 | Human Gate 표 | 유지 | 표 자체는 프로젝트 문서 그대로. Paseo 특유 게이트 행위 추가 제안: relay 사용 포함(Q9, 사용자 결정 대기) | common §7 |
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
| C11 | Orca hook·statusLine 전역 설치 | 보류 | 병행기 종료 기준(Q1) 충족 후 3단계에서 정리. 이 초안은 전역 설정을 건드리지 않음 |
| C12 | Kanban tr:id 혼재 | 보류 | 무관 |
| C13 | 깨진 orcahq gateway, korean-law MCP | 보류 | 운영 정리 항목. 사용자 결정 |
| C14 | Task 정책 설치 편차 | 보류 | Paseo 정책도 Task 정책을 필수로 요구하지 않음(기존과 동일) |
| C15 | README "자동 설치 없음" vs `ai_policy.install` | 보류 | 단, 설치기·번들이 Orca 전용(`REQUIRED`에 `orca-common.md`, 설치 경로 `.config/ai-agent-policy/orca`)이므로 Paseo 번들 설계 시 함께 정리(3단계) |

## 5. 결정 사항과 열린 질문

사용자 확정(2026-11-25): Q1·Q2·Q4·Q5는 «결정됨», Q3는 방향 확정 후 같은 날 시험 결과를 받아 «확정»했다. 나머지(Q6~Q10)는 열린 질문이다.

**Q1. Orca 정책 퇴역 시점 — «결정됨»: 병행기 후 퇴역**
- **병행기의 정의**: 결정 시점에 기존 Orca가 소유한 진행 중 Run·worktree만 Orca 규칙(`orca-common.md`, `orca-worker-lifecycle.md`)으로 마무리한다. 새 Task는 즉시 Paseo 규칙을 쓴다. 이미 Orca가 소유한 Run을 Paseo로 옮기거나 새 Run을 Orca에 추가하지 않는다.
- **종료 기준**: 모든 Orca Run이 정산되고 그 Run의 Dispatch가 release 처리된 시점(상태가 released이거나, release_pending/release_unknown이면 원인과 사용자 판단이 기록된 상태). 활성·불확실·사용자 소유 세션은 종료 기준을 채운 것으로 보지 않는다.
- **확인 방법**: (1) 사용자 Task 연결표와 Task 로컬 기록에서 Orca Run ID 목록을 만든다. (2) 각 Run을 `orca orchestration run-show`로 조회해 정산·release 상태를 확인한다(명령 형태는 확인 시점의 Orca CLI 도움말로 재확인). (3) 목록의 모든 Run이 종료 기준을 만족하고 새로 생긴 Orca Run이 없음을 확인한 결과를 기록한다. 확인 근거 없이 종료로 판단하지 않는다.
- **종료 후 조치**: `orca-*` 문서·`policy/orca-common.md`에 «보관» 표시(내용 삭제 아님). 전역 Orca hook·statusLine·theme(C11) 정리도 이 시점 이후 3단계에서 사용자 승인으로 진행한다.
- 근거: 진행 중 Run/Dispatch 정산 규칙이 사라지면 정리 상태가 불명확해진다.

**Q2. 프로젝트 실행 차단(guard.py)의 Paseo 모드 — «결정됨»: Git 기반 Paseo 모드 추가, 순서 조건 명시**
- **순서 조건**: (1) `paseo.json` setup 훅으로 정책(guard·hook 설정) 설치를 자동화한다. (2) 새 세션에서 hook이 실제로 로딩되는지 확인한다. (3) 그 뒤에만 guard의 Paseo 모드를 켠다. 1·2가 끝나기 전에 Paseo 모드를 켜지 않는다(hook이 안 돌면 검사가 없는 것과 같다).
- **범위(최소)**: 작업 위치가 Paseo worktree 루트 아래인지, 브랜치, worktree 생성 기준 SHA, Task 연결표 일치, 기본 체크아웃 쓰기 거부를 Git 정보로 검사한다. Paseo 메타데이터 의존은 최소화한다.
- **한계 유지**: guard는 완전한 샌드박스가 아니다(기존 한계 문구 유지). 우회 가능성을 문서에 남긴다.
- **L4 검토**: guard는 집행 코드다. 2단계 구현 전에 Opus high(LEVEL 4) 설계 검토와 구현 후 독립 검토를 거친다.
- 근거: 현재 7개 사본(gh-docs + 6개 저장소)의 Orca 모드는 Paseo 세션에서 통과 조건을 만들 수 없어 일반 작업이 막히거나 우회가 생긴다.

**Q3. Codex 리뷰어(`review-claude-work`)의 읽기 전용 보장 — «확정»(2026-11-25 시험 결과 반영)**
- 방향: 계열 교차 리뷰를 유지하되, 도구 수준 강제를 증명하지 못한 수단을 «강제»라고 쓰지 않는다.
- 사실: Codex에는 `plan_mode` 토글(`features.plan_mode`, «planning-only collaboration mode»)이 있다(`inspect_provider`). Paseo는 Codex 읽기 전용 샌드박스 모드를 노출하지 않는다(modes: auto, auto-review, full-access). 샌드박스는 workspace-write다.
- 시험·결과·한계: routing 문서 2.1절과 7.1의 C-8(지침 수준 준수 확인), 7.2의 U-4·U-15(도구 수준 강제 미확인).
- **확정 규칙**: (1) `review-claude-work`에 `features.plan_mode=true`를 켜는 것을 권장한다. (2) «읽기 전용이 강제된다»고 주장하지 않는다. 읽기 전용 증거는 리뷰 전후 `git status`/diff 동일 확인(무변경 검사)이며 필수다. (3) 쓰기 차단이 반드시 필요한 중요 리뷰(보안·무결성 등)는 Claude `plan` 모드 리뷰어를 쓴다(계열 교차 포기, 모드 설명상 강제). Claude `plan`은 «도구 실행을 막는 모드로 설명됨», 이 세션에서 쓰기 시도로 검증하지 않았다. (4) 프로필 modeId가 `auto`이므로 plan_mode를 켜는 변경은 routing 문서 제안 P6로 두고 사용자 승인 후 프로필 설정에 반영한다. 이 단계에서 `~/.paseo/config.json`은 수정하지 않았다.

**Q4. Claude Worker의 Paseo 도구(재위임 수단) 제한 — «결정됨»: 정책 규칙 + Owner의 자식 목록 점검으로 시작**
- 관측(2026-11-25 `~/.paseo/config.json` 읽기, 값 출력 없음): `claude` 제공자는 터미널·워크스페이스 스크립트 도구만 `disabledTools`로 막고 `create_agent`·`send_agent_prompt`는 열려 있다. `codex` 제공자는 `paseoTools.enabled=false`라 Paseo 도구가 전부 없어 재위임이 불가능하다. 따라서 **재위임 위험은 Claude Worker에 한정**된다.
- 보고용 `send_agent_prompt`는 막을 수 없다(데몬 프로토콜이 의존한다).
- 시작 규칙: 재위임 금지 정책 + Owner가 정산 때 `list_agents`와 부모 라벨로 원장에 없는 손자 에이전트를 점검하고 발견 시 보고한다.
- 필요 시 후속 방안: Worker 전용 custom provider 별칭으로 `create_agent`만 `disabledTools`에 넣는다. **검증이 필요**하며(미확인 목록 참조) 보안 경계가 아니다. 같은 `claude` provider를 쓰는 Root·Coordinator가 막히지 않게 별칭을 분리해야 한다.

**Q5. 데몬 운영 방식과 환경 전파 — «결정됨»: 현 상태를 기준으로 명문화하고 시작 시 점검 항목으로 둔다(바꾸지 않는다)**
- 관측 사실(2026-11-25): 데몬은 `desktopManaged=false`인 독립 데몬이고, 에이전트 셸 로케일은 `ko_KR.UTF-8`이며, 에이전트 셸에 `ANTHROPIC_BASE_URL` 환경변수가 없다.
- 시작 시 점검 항목(값은 기록하지 않음): `paseo daemon status`의 `desktopManaged`, 에이전트 셸 `LANG`/`LC_ALL`, 프록시·API 키 환경변수 존재 여부, relay 상태, 비밀번호 설정 여부. 항목은 lifecycle 10절에 둔다.
- 데몬 방식을 바꾸는 권고((a) CLI 데몬 재기동, (b) `keepRunningAfterQuit`)는 정책으로 채택하지 않는다. 점검 결과가 달라지면 사용자에게 보고한다.
- 기존 전역 정책의 `ANTHROPIC_BASE_URL` 프록시 설정 유지 여부는 이번 관측(에이전트 셸에 없음)으로 결정되지 않는다. 필요해질 때 사용자 결정이다.

그 밖의 질문:

- Q6. 기본 스킬 경로 표의 Paseo 조율 스킬: `paseo` 스킬 사용 vs 이 정책 전용 신규 스킬. 권장: 기존 `paseo` 스킬 + 이 문서 참조.
- Q7. Coordinator Sonnet high를 `model-routing.json`에 반영(제안 P2)할지. 권장: 반영(사용자 승인 이미 있음).
- Q8. Hermes를 계속 사용자 업무 관리자로 쓸지. 쓰지 않으면 MUST-PRESERVE 3의 Hermes 문구를 조건부로 남긴다.
- Q9. Paseo 특유 행위의 Human Gate 추가 여부: **relay 사용 여부**, 플러그인 설치, `archive_workspace`, schedule 생성(비용 발생), 권한 모드 상향. 권장: 공통 게이트로 추가. 현재 상태(F3): `daemon.relay.enabled=true`이며 `daemon.*`에 비밀번호 계열 키가 없고 `cors.allowedOrigins`는 기본값이다(2026-11-25 설정 파일 읽기, 값 출력 없음). 조사 문서(`paseo-technical-research.md` 2절·Top risks)는 «relay는 끄고 비밀번호를 설정»을 권고했다. **켜진 의도는 미확인이며 사용자 확인 필요**하다. 정책은 임의로 끄거나 설정을 바꾸라고 쓰지 않고, 사용자 결정 전까지 현 상태를 기록·보고만 한다.
- Q10. Owner 원장 위치: Task 로컬 기록 폴더(`LOCAL_ARTIFACT_ROOT/<TASK_ID>/`) vs Paseo 라벨만. 권장: 로컬 기록(라벨 필터가 없음).

## 6. 후속 단계별 영향 파일

### 2단계: GH 프로젝트 (사용자 승인 후)

- `gh-docs/docs/guides/orca/ORCA_POLICY.md`, `MODEL_ROUTING.md`, `WORKTREE_RULES.md`, `INSTALLATION.md` → Paseo 판으로 재생성 또는 대체(위치·이름은 2단계 결정). Human Gate 표(ORCA_POLICY.md 38행~)는 의미 그대로 이전.
- `gh-docs/docs/guides/TASK_POLICY.md`: Orca Task/Run/Dispatch 참조를 Paseo agentId·workspaceId로, 연결표 열 이름.
- `scripts/ai-policy/guard.py`, `install.py`, `test_guard.py` 7개 사본: gh-docs, gh-rag-provider, New-Backend-RiskZero3, New-Batch-RiskZero3, New-Frontend-Riskzero3, New-Mobile-Backend-Riskzero, New-Mobile-Riskzero3(2026-11-25 `find` 확인). Orca 모드 → Paseo 모드(Q2). **순서**: setup 훅 정책 설치 자동화 → 새 세션 hook 실제 로딩 확인 → Paseo 모드 활성화. guard는 집행 코드이므로 **구현 전 설계와 구현 후 변경을 L4(Opus high)가 검토**한다. Orca 모드 제거는 병행기 종료 기준(Q1) 충족 뒤에만 한다.
- 6개 저장소 정책 스냅샷과 진입 파일(AGENTS.md/CLAUDE.md 관리 블록, v1.0.4/1.0.5), GH 공통 폴더 `AGENTS.md`·`CLAUDE.md`·`.orca/AGENTS.md`.

### 3단계: 이 저장소와 전역 설정 (사용자 승인 후)

- 이 저장소: `README.md`(Orca 전략 절), `orca-project-setup.md` → `paseo-project-setup.md` 신규, `project-task-policy-setup.md` POLICY F(Orca 결합 문구), `claude-code-global-model-routing-prompt.md`, `codex-global-model-routing-prompt.md`, `policy/model-routing.json`(제안 P1~P5), `policy/bundle.json`·`policy/adapters/*`, `ai_policy/bundle.py`(`REQUIRED`), `ai_policy/install.py`(설치 경로·마커가 orca 전용), `ai_policy/context.py`(ORCA_* 감지), `ai_policy/routing.py`(`--host paseo`), `tests/*`, `docs/reproducible-orca-environment.md`, 기존 `docs/orca-*.md`·`policy/orca-common.md`(병행기 종료 기준(Q1) 충족 후 «보관» 표시).
- 전역: `~/.claude/CLAUDE.md`("Confirmed Orca tasks" 절, 기본 경로 표 구현 조율 행, Runtime notes), `~/.codex/AGENTS.md`(Orca 단락), `~/.claude/settings.json`·`~/.codex/hooks.json`의 Orca hook·statusLine·theme(C11).
- 연관(정책 외, 영향만 기록): task-radar의 Orca 요청 outbox·relay-keeper, Hermes work-manager `policy.json`·orca-status 플러그인, `com.orcahq.gateway` launchd(C13), 볼트 `02_Projects/Orca/README.md`(C6), `~/.claude/skills`의 orca-* 스킬.

## 7. 확인됨과 미확인 목록

### 7.1 확인됨 (일자·방법)

| # | 확인 내용 | 일자·방법 | 반영 위치 |
|---|---|---|---|
| C-1 | 데몬이 모든 에이전트에 `daemon.appendSystemPrompt`로 조율 규칙(부모 보고 접두어 `PROJECT_DONE:`/`BLOCKED:`/`NEED_APPROVAL:`+증거, 자식 종료 알림≠완료, 폴링 금지, 권한 요청은 대상 저장소·`~/.paseo/worktrees` 안에서만 승인, archive·push 금지)를 주입한다 | 2026-11-25, 이 세션이 받은 시스템 지침과 Worker 보고(PROJECT_DONE/BLOCKED)가 실제로 그 방식으로 도착한 것을 관측 | common §5, lifecycle §7 |
| C-2 | `claude` 제공자는 터미널·워크스페이스 스크립트 도구만 `disabledTools`로 막고 `create_agent`·`send_agent_prompt`는 열려 있다. `codex` 제공자는 `paseoTools.enabled=false`로 Paseo 도구가 없다 | 2026-11-25, `~/.paseo/config.json` 읽기(값 출력 없음) | common §2, 5절 Q4 |
| C-3 | 데몬은 `desktopManaged=false`인 독립 데몬, 에이전트 셸 로케일 `ko_KR.UTF-8`, 에이전트 셸에 `ANTHROPIC_BASE_URL` 없음 | 2026-11-25, 부모 프롬프트의 관측 | lifecycle §10, 5절 Q5 |
| C-4 | `daemon.relay.enabled=true`, `daemon.*`에 비밀번호 계열 키 없음, `cors.allowedOrigins` 기본값 | 2026-11-25, 설정 파일 읽기(값 출력 없음) | common §6·§7, 5절 Q9 |
| C-5 | Codex에 `plan_mode` 토글(`features.plan_mode`, «planning-only collaboration mode»)이 존재한다(지침 수준 준수는 C-8, 도구 수준 강제는 미확인 U-4·U-15) | 2026-11-25, `inspect_provider` | routing §2, 5절 Q3 |
| C-6 | Codex 기본 권한(auto) 에이전트는 Paseo worktree에서 `git add/commit`이 실패한다. Git 메타데이터(`.git/worktrees/...`)가 작업 폴더 밖 원본 저장소 `.git`에 있어 샌드박스가 `index.lock` 생성을 거부(Operation not permitted) | 2026-11-25, 이 세션 Codex Worker의 실패 관측 | common §3, lifecycle §5·§7 |
| C-7 | 프로필 메모·목록(2026-11-25 `list_profiles`)의 provider/model/mode/thinking 값 | 2026-11-25, `list_profiles` | routing §2 |
| C-8 | Codex(`gpt-6-luna`, `auto`, `features.plan_mode=true`) 시험 2회: 읽기(`ls`, `pwd`)만 실행하고 셸·편집 도구 파일 생성은 «모드 지침 때문에» 시도하지 않았다. 사용자가 임시 폴더 한정 쓰기를 명시 허용한 2차에도 «Plan 모드 지침이 파일 변경을 금지하므로 시도할 수 없다»며 거부했고 폴더에 파일 0개. 즉 **지침 수준 준수는 확인됨**. 응답이 «도구/샌드박스가 막은 것이 아니라 내가 안 한 것»이라고 명시했으므로 **도구 수준 강제는 증명되지 않음** | 2026-11-25, Paseo Codex 에이전트 시험 2회(폴더 파일 수 확인) | routing §2.1, 5절 Q3 |

연결: C-6은 아래 미확인 U-3(hook·AGENTS.md 로딩)·U-4(Codex 읽기 전용)와 연결된다. 쓰기 거부가 실제로 집행된다는 점은 확인했지만 이것이 «쓰기·셸을 전부 막는 읽기 전용 모드가 있다»는 증거는 아니다(U-4). 또한 Codex 세션에서 정책 설치·hook 검증에 git 연산이 필요하면 같은 제약에 걸릴 수 있으므로 그 단계는 Claude Worker 또는 Owner가 맡는다(U-3).

### 7.2 미확인

런타임 실행으로 검증하지 않았거나 조사 문서에 근거가 없는 항목이다. 번호는 기존 1~13번을 유지했고(확인된 일부는 «부분 확인»), 새 항목은 14번부터다(Q3 시험으로 15번에 한계를 기록하고 20번을 추가했다).

1. 〔U-1〕 `get_agent_status` 스냅샷에 실제 실행 model·thinking이 나오는지(요청값 대비 확인 경로).
2. 〔U-2〕 `create_workspace.baseBranch`가 원격 ref(`origin/dev`)를 받는지, 로컬과 원격이 다를 때의 동작.
3. 〔U-3〕 Paseo 경유 Claude 세션에서 프로젝트 hook(guard)이 실제 실행되는지, Codex app-server 세션이 AGENTS.md를 읽는지. Q2 순서 조건 (2)의 확인 대상이다. C-6으로 Codex 샌드박스 제약이 확인되어, Codex 세션의 정책 설치·commit 가능 여부도 함께 본다.
4. 〔U-4〕 Codex에 읽기 전용(쓰기·셸 차단) 모드가 있는지(`auto-review`의 의미 포함). **부분 확인**: `plan_mode` 토글 존재(C-5)와 지침 수준 준수(C-8)는 확인됨. Paseo는 읽기 전용 샌드박스 모드를 노출하지 않으며(auto, auto-review, full-access) 쓰기·셸을 도구·샌드박스 수준에서 막는 모드는 **미확인**. 정책은 «강제 아님 + 무변경 검사»로 확정(Q3).
5. 〔U-5〕 Owner가 `closed` 상태일 때 완료 알림이 전달·재개되는지(#8464 관련).
6. 〔U-6〕 손자 에이전트 생성(중첩 오케스트레이션)의 실제 동작과 깊이 제한. Q4 점검 규칙이 대상으로 삼는다.
7. 〔U-7〕 `labels` 키 규칙의 예약어 충돌 여부, `list_agents`의 라벨 조회 방법.
8. 〔U-8〕 에이전트별 토큰·비용을 MCP로 얻는 방법(SDK `lastUsage`만 문서화).
9. 〔U-9〕 **부분 확인**: 데몬 실행 방식·locale·`ANTHROPIC_BASE_URL`·relay·비밀번호 키·CORS·도구 주입 설정은 C-2~C-4로 확인됨. 남은 것: 비밀번호 설정 필요성, relay 의도(14번), 프록시·API 키 환경변수 중 `ANTHROPIC_BASE_URL` 외 항목의 존재 여부.
10. 〔U-10〕 프로필 메모의 `gpt-6.2-sol`/`gpt-6.2-astra`와 json 고정 ID(`gpt-6.1-sol`/`gpt-6-astra`) 차이의 원인.
11. 〔U-11〕 `#8436` 메시지 유실, `#7760` Codex 턴 후 정지가 v0.17.x에서 남아 있는지.
12. 〔U-12〕 Claude Agent SDK 경유 구독 사용의 Anthropic 측 약관·과금 처리.
13. 〔U-13〕 `paseo.json` setup 훅으로 정책 설치를 자동화할 수 있는지와 그 실패 시 동작. Q2 순서 조건 (1)의 확인 대상이다.
14. 〔U-14〕 **사용자 확인 필요**: relay가 켜져 있는 의도와 비밀번호 필요 여부. 현재 상태는 켜짐·비밀번호 키 없음(C-4)이며 조사 문서 권고와 다르다. 임의 변경 금지, Q9로 사용자 결정.
15. 〔U-15〕 `plan_mode`가 도구·샌드박스 수준에서 쓰기·셸을 막는지: **미확인**. 2026-11-25 시험은 지침 수준 준수만 보였다(C-8). 이 시험으로 증명할 수 없으며, 증명 전까지 정책은 강제를 주장하지 않는다. 한계: 시험 2회, 모델 `gpt-6-luna` 한 종류, 에이전트의 거부가 지침 해석에 의존. 다른 모델·지침 변경 시 결과가 달라질 수 있다.
16. 〔U-16〕 Worker 전용 custom provider 별칭으로 `create_agent`만 `disabledTools`에 넣을 수 있는지와 `claude` provider 설정을 공유하는 Root·Coordinator에 영향이 없는지(Q4 후속 방안).
17. 〔U-17〕 Codex Worker commit을 막는 샌드박스 제약을 권한 모드 상향 없이 해소하는 지원 설정(예: 쓰기 가능 경로)이 있는지. 현재 규칙은 «commit하지 않는다»이며 우회 방안은 사용자 승인 사항이다(C-6).
18. 〔U-18〕 `appendSystemPrompt` 주입이 Codex 에이전트에도 적용되는지와 그 내용·접두어가 데몬 버전·설정 변경 시 달라질 수 있는지. 정책은 접두어 문구를 인용하므로 시작 점검에서 주입 내용을 다시 확인한다(값 아닌 규칙 존재 여부).
19. 〔U-19〕 Orca Run 열거·정산 상태를 한 번에 확인하는 방법. 병행기 종료 확인(Q1)은 Task 연결표·로컬 기록 + `run-show`로 하며, 전체 Run 목록을 자동으로 얻는 CLI 경로는 확인하지 않았다.
20. 〔U-20〕 Claude `plan` 모드가 실제로 쓰기·셸을 막는지: Paseo 모드 설명(«Analyze the codebase without executing tools or edits»)으로 도구 실행을 막는 모드로 설명되나 이 세션에서 쓰기 시도로 검증하지 않았다. 중요 리뷰에 쓰기 전에 첫 사용 시 확인한다.
