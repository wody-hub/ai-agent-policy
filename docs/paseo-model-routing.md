# Paseo 모델 라우팅 (draft 0.1.0)

상태: 초안(2026-11-25, 같은 날 사용자 확정 결정 반영, Q3 Codex 리뷰어 읽기 전용은 2026-11-25 시험 결과로 확정: plan_mode 권장, 강제 주장 금지, 무변경 검사 필수). 정본 값은 [`policy/model-routing.json`](../policy/model-routing.json)(1.5.0)이며 이 문서는 그 값을 Paseo 프로필에 대응시키는 규칙이다. `model-routing.json`은 이번 단계에서 수정하지 않았고, 변경은 4절에 "제안"으로만 적는다. Orca용 세부 유형표는 [Orca 작업 유형별 모델 라우팅](orca-model-routing.md)을 그대로 쓴다.

## 1. 원칙

- **프로필은 시작 구성이다.** Paseo 프로필은 provider·model·mode·thinking 묶음과 "When to use" 메모일 뿐이고, `create_agent`에는 프로필 매개변수가 없어 Owner가 필드를 복사해 넣는다 [DOC mcp.md]. Paseo에는 라우팅·승격·재시도 계산 기능이 없다 [DOC research Top risk 7].
- **판정은 Owner가 한다.** 작업 유형·레벨 판정, 프로필 선택, 시도 횟수, 승격, 대체 모델, 동시 실행 한도는 Root/Coordinator가 이 문서와 `model-routing.json`으로 결정하고 이유를 기록한다.
- **실행 중 세션의 모델을 바꾸지 않는다.** 선택 결과는 새 Worker의 시작 구성이다. `update_agent`로 진행 중 Worker의 모델을 바꾸는 것은 승격으로 보지 않는다(이 경우 시도 이력·문맥이 섞인다). 승격은 새 Worker + 구조화 인계로 한다.
- 요청값(프로필)과 실제 실행값을 구분해 기록한다. 상태 스냅샷에서 실제 model·thinking을 확인할 수 있는지는 [미확인]이다.

## 2. 프로필 대응표 (2026-11-25 `list_profiles` 확인값)

| Paseo 프로필 | provider/model · mode · thinking | 정본 라우팅 항목(host orca) | 일치 여부 |
|---|---|---|---|
| `root-orchestrator` | claude/claude-sonnet-5-5 · auto · high | `roles.root_orchestrator`: Terra high → 대체 Sonnet high | 대체 경로 사용. 사유: Codex에 Paseo 도구 없음(사용자 승인 2026-11-25) |
| `project-coordinator` | claude/claude-sonnet-5-5 · auto · high | `roles.project_coordinator`: Luna high → 대체 Terra high | **불일치.** Sonnet high는 json의 대체 목록에 없다. 사용자 승인(2026-11-25)은 있으나 json 반영 필요(4절 제안 P2) |
| `dev-l1-simple` | codex/gpt-6-luna · auto · medium | `levels.1`: Luna medium | 일치 |
| `dev-l2-general` | codex/gpt-6-luna · auto · high | `levels.2`: Luna high → Sonnet high | 일치(대체는 프로필 없음, 필요 시 Sonnet high로 수동 구성) |
| `dev-l3-complex` | claude/claude-sonnet-5-5 · auto · high | `levels.3`: Sonnet high → Terra high | 일치 |
| `l4-critical` | claude/claude-opus-5-5 · auto · high | `levels.4`: Opus high → Sol high | 일치. 프로필 메모의 대체 ID `gpt-6.2-sol`은 json 고정 ID `gpt-6.1-sol`과 다르다(캐시 해석 결과인지 [미확인]) |
| `l5-last-resort` | claude/claude-fable-5-1 · auto · high | `levels.5`: Fable high → Astra high | 일치. 메모의 `gpt-6.2-astra` vs json `gpt-6-astra` 동일 사유 [미확인] |
| `review-codex-work` | claude/claude-sonnet-5-5 · **plan** · medium | `code_review_codex`: Sonnet medium(중요 시 `important_review_codex` Sonnet high) | 일치. plan 모드로 읽기 전용 |
| `review-claude-work` | codex/gpt-6.1-terra · auto · high | `code_review_claude`: Terra high → Luna high | 모델 일치. 읽기 전용이 모드로 강제되지 않는다(메모: "Instruct read-only"). `features.plan_mode=true`를 켜는 것을 권장하나(제안 P6, 사용자 승인 후 프로필 반영) 지침 수준 보호일 뿐 **강제가 아니다**. 읽기 전용 증거는 리뷰 전후 `git status`/diff 무변경 검사(필수). 2.1절 |
| `lookup` | codex/gpt-6-luna · auto · medium | `roles.lookup`: Luna medium, `log_summary`: Luna low | 일치(log_summary는 thinking low로 변경해 생성) |

### 2.1 Codex 리뷰어 읽기 전용 (Q3, 2026-11-25 확정)

**시험(2026-11-25, Codex `gpt-6-luna`, modeId `auto`, `features.plan_mode=true`)**
- 1차: 읽기(`ls`, `pwd`)만 실행·성공. 셸 파일 생성(`echo > probe1.txt`)과 편집 도구 파일 생성은 «모드 지침 때문에 시도하지 않음».
- 2차: 오케스트레이터가 임시 폴더 한정 쓰기를 명시 허용했는데도 «Plan 모드 지침이 파일 변경을 금지하므로 시도할 수 없다»며 거부. 폴더는 끝까지 비어 있었다(파일 0개 확인). 응답이 «도구/샌드박스가 막은 것이 아니라 내가 안 한 것»이라고 명시했다.
- 해석: `plan_mode`는 **지침 수준 제한**으로 매우 견고하게 지켜졌다. 그러나 도구·샌드박스가 쓰기를 거부한 것이 아니므로 **도구 수준 강제 여부는 미확인**이며 이 시험으로 강제를 증명할 수 없다. Codex 샌드박스는 workspace-write이고(작업 폴더 밖 `.git` 메타데이터 쓰기 거부 실측, common §2) 읽기 전용 샌드박스 모드는 Paseo가 노출하지 않는다(modes: auto, auto-review, full-access).

**확정 규칙**
1. Codex 리뷰어(`review-claude-work`)는 `features.plan_mode=true`를 켜는 것을 **권장**한다(지침 수준 보호).
2. 그러나 «읽기 전용이 강제된다»고 주장하지 않는다. 읽기 전용의 증거는 **리뷰 전후 대상 worktree의 `git status`/diff가 같다는 확인(무변경 검사)**이며 이 검사는 필수다. 변경이 생기면 리뷰 결과를 무효로 하고 원인과 함께 보고한다(되돌리지 않고 Owner가 판단).
3. 쓰기 차단이 반드시 필요한 중요 리뷰(보안·무결성 등)는 **Claude `plan` 모드 리뷰어**를 쓴다. 계열 교차를 포기하는 대신 모드 설명상 도구 실행이 막힌다. Claude `plan` 모드는 «도구 실행을 막는 모드로 설명됨(Paseo 모드 설명: «Analyze the codebase without executing tools or edits»)»이며 이 세션에서 쓰기 시도로 검증하지는 않았다.
4. `review-claude-work`의 modeId가 `auto`이므로 plan_mode를 켜는 프로필 변경은 **제안 P6**(5절)로 두고 사용자 승인 후 프로필 설정에 반영한다. 이 단계에서 `~/.paseo/config.json`은 수정하지 않았다.
5. 리뷰어는 commit하지 않는다(Codex는 Paseo worktree에서 commit이 막히고 권한 모드를 올려 우회하지 않는다).

세부 작업 유형(`requirements`, `decomposition`, `architecture`, `refactor_design`, `db_design`, `test_design` 등)이 Terra high나 Sonnet high를 기본으로 지정하는 경우, 맞는 프로필이 없으면 Owner가 정본 값으로 `provider`·`thinkingOptionId`를 직접 구성하고 선택 이유를 기록한다. 이를 위해 프로필을 새로 만들거나 바꾸는 것은 사용자 승인 사항이다.

## 3. 선택 절차

1. 우선순위대로 판정: 필수 고위험 전문 경로(`high_risk_types`, LEVEL 4 유형) → 프로젝트·사용자 명시 지정 → 단순 작업 조건(명확한 소범위·자동 검증 가능·저위험을 모두 충족하면 LEVEL 1) → 작업 유형(`orca_task_routes`) → 복잡도 기본값(`levels`).
2. 저장소 checkout이 있으면 현재 라우터를 `--host orca`로 실행해 같은 판정을 얻는다: `python3 -B -m ai_policy.routing --host orca --task-type <유형>`(또는 `--role`, `--level`, `--failures`, `--failure-kind`, `--available`). `action`이 `blocked_no_available_model`(종료 40)·`handoff_to_lead`(종료 41)이면 Worker를 만들지 않고 상위 Owner에 보고한다. 출력의 `orca_worker_args`는 Orca 전용이므로 쓰지 않고, 선택된 model·effort를 2절 프로필 또는 직접 구성으로 옮긴다. `--host paseo` 지원은 제안(P1)이며 아직 없다.
3. 선택된 tool·model·effort를 프로필에 대응시키고, 없으면 직접 구성한다. Codex 모델 ID는 30일 이내 `models_cache.json`에서 계열별로 해석하며, `pinned_fallback`이면 캐시를 갱신한 뒤 다시 확인한다. Paseo가 보여 주는 모델 목록(`list_models`)과 대조한다.
4. 고위험 작업은 처음부터 LEVEL 4(`l4-critical` 또는 Sol high)로 분석·검토한다. 구현은 가능하면 LEVEL 2·3 Worker가 이어받는다.
5. 리뷰어는 구현자와 다른 도구 또는 독립 컨텍스트로 한다: Codex 구현 → `review-codex-work`, Claude 구현 → `review-claude-work`.
6. 선택 이유(라우터 JSON 또는 판정 근거), 프로필 id, 요청값, 확인한 실행값을 원장에 남긴다.

## 4. 시도·승격·한도 계산 (Owner 책임)

| 항목 | 정본 값 | Paseo에서의 이행 방법 |
|---|---|---|
| 판단 실패 시도 | 근본 문제당 2회(`max_attempts_per_executor`) | Owner 원장에 (Task, 근본 문제, 시도 번호, 실패 종류, 프로필) 기록. 2회 실패 후 다음 레벨 프로필로 새 Worker. 모델 교체가 횟수를 초기화하지 않음 |
| 비모델 재실행 | 원인당 최대 3회(`max_run_attempts_non_model`) | Paseo 데몬 중단, 메시지 유실, `error` 상태 중 환경·권한·도구 원인, 프로바이더 로그인 실패를 여기로 분류. 같은 프로필 유지. 3회째 실패 시 상위 Owner/사용자에게 |
| 즉시 LEVEL 4 | 요구사항 모순·구조 위험·데이터 무결성 위험 | 해당 판단을 받은 Owner가 즉시 `l4-critical`로 분석 Worker 생성 |
| LEVEL 5 | LEVEL 4가 같은 문제에서 2회 실패한 뒤만 | `l5-last-resort` 생성 전 LEVEL 4 실패 2회 근거를 원장에서 확인 |
| LEVEL 5 실패 2회 | 자동 승격 중단 | 증거와 필요한 결정을 사용자에게 |
| 동시 Worker | 3 | Paseo에 상한 없음 [SRC]. Root가 `list_agents`(statuses `initializing`,`running`, 미정산 `idle`)와 원장으로 전체 수를 센다. Coordinator는 배정 전 Root가 허용한 슬롯 안에서만 생성 |
| 동시 프리미엄 | 1(premium·exceptional tier) | `l4-critical`, `l5-last-resort`, Sol/Astra 직접 구성이 대상. Root가 단일 슬롯을 관리하며 사용 이유를 기록 |
| 승격 인계 | goal, related_files, current_state, errors, attempts, hypotheses, decision_needed | 새 Worker의 초기 프롬프트에 이 항목만 넣는다 |
| 해결 후 | 기본 레벨 복귀 | 후속 Worker는 원래 레벨 프로필로 |

비모델 실패 분류 추가(Paseo 특유): 알림 미도착, 수락 후 시작 근거 없음, 데몬 재시작으로 `closed`, 권한 요청 대기, `ANTHROPIC_BASE_URL`·로그인 환경 문제(#3618), 한국어 locale 문제(#3513), Codex Worker의 Paseo worktree `git add/commit` 샌드박스 거부(Git 메타데이터가 작업 폴더 밖, 2026-11-25 관측). 이것들은 승격 사유가 아니다. Codex commit 거부는 재시도하거나 권한 모드를 올려 우회하지 않고, «Codex Worker는 commit하지 않음» 규칙대로 diff 보고 후 Claude Worker 또는 Owner가 commit한다.

## 5. `model-routing.json` 변경 제안 (미적용)

- **P1 host 추가**: `hosts.paseo = {"tools": ["claude","codex"], "orchestrator_tools": ["claude"], "description": "Confirmed Paseo task: orchestrators must have Paseo tools (Claude); workers may be Claude or Codex."}`. 라우터에 `--host paseo` 출력(`paseo_create_agent`: `provider`, `settings.modeId`, `settings.thinkingOptionId`, 추천 프로필 id)을 추가하고 `orca_worker_args`는 orca host에서만 낸다. 기존 `--host orca` 결과는 바꾸지 않는다.
- **P2 역할 기본값**: Paseo host에서 `root_orchestrator = sonnet high`, `project_coordinator = sonnet high`(대체 없음 또는 opus는 금지). Codex 계열은 Paseo 도구가 주입되기 전까지 오케스트레이터 후보에서 제외.
- **P3 프로필 매핑 블록**: `paseo_profiles = {"root-orchestrator": {"role": "root_orchestrator"}, "dev-l1-simple": {"level": 1}, ...}`로 2절 표를 기계가 읽을 수 있게 둔다. 프로필 실제 값은 Paseo 설정이 정본이므로 json에는 이름 대응만 둔다.
- **P4 읽기 전용 리뷰 mode**: `review_mode = {"claude": "plan", "codex": {"mode": "auto", "plan_mode": true, "enforced": false, "evidence": "git_status_diff_unchanged"}}`. Codex 쪽은 지침 수준 보호이며 `enforced: false`로 기록한다(2.1절).
- **P6 Codex 리뷰어 프로필의 plan_mode**: `review-claude-work` 프로필에 `features.plan_mode=true`를 켠다(modeId는 `auto` 유지). 사용자 승인 후 Paseo 프로필 설정에 반영하며 이 단계에서는 설정 파일을 수정하지 않았다. 반영 후 새 리뷰어 세션에서 plan_mode 적용과 무변경 검사를 첫 사용 시 확인한다.
- **P5 Codex 고정 ID 확인**: 프로필 메모의 `gpt-6.2-sol`/`gpt-6.2-astra`가 현재 캐시 해석 결과로 확인되면 fallback ID 갱신 여부를 검토. 확인 전에는 바꾸지 않는다.
- 버전은 1.6.0(가칭), `verified_on`은 실행 확인일로 기록한다.
