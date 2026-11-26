# Paseo 모델 라우팅 (0.2.0)

상태: 승인(2026-11-26). 미검증 모델 접근과 임시 프로필은 별도로 표시한다. Codex 리뷰어 plan_mode는 권장 사항이며 강제 차단으로 보지 않고 무변경 검사를 한다. **정본은 [`policy/model-routing.json`](../policy/model-routing.json)(1.7.1)이다.** Paseo 프로필의 provider·model·modeId·thinkingOptionId·notes는 JSON의 `paseo_profiles`에서 파생되며, `python3 -B -m ai_policy.paseo check|sync`가 `~/.paseo/config.json`과 대조·반영한다(6절). `sync`는 앞의 네 필드만 맞추고 `notes`는 프로필을 새로 만들 때만 쓴다(기존 프로필의 `notes` 차이는 `check`의 `notes_differ` 정보로만 보인다). 이 문서는 그 값을 Paseo 프로필에 대응시키는 규칙이다. 1.7.0은 1.6.0(P1~P4)과 main의 수평 단계·교차 계열 리뷰 변경을 합친 것이고 P5를 적용했다(5절). 라우터는 `--host paseo`를 지원한다. 세부 유형표는 [공통 작업 유형 라우팅](task-model-routing.md)을 사용한다.

## 1. 원칙

- **프로필은 시작 구성이다.** Paseo 프로필은 provider·model·mode·thinking 묶음과 "When to use" 메모일 뿐이고, `create_agent`에는 프로필 매개변수가 없어 Owner가 필드를 복사해 넣는다 [DOC mcp.md]. Paseo에는 라우팅·승격·재시도 계산 기능이 없다 [DOC research Top risk 7].
- **판정은 Owner가 한다.** 작업 유형·레벨 판정, 프로필 선택, 시도 횟수, 승격, 대체 모델, 동시 실행 한도는 Root/Coordinator가 이 문서와 `model-routing.json`으로 결정하고 이유를 기록한다.
- **실행 중 세션의 모델을 바꾸지 않는다.** 선택 결과는 새 Worker의 시작 구성이다. `update_agent`로 진행 중 Worker의 모델을 바꾸는 것은 승격으로 보지 않는다(이 경우 시도 이력·문맥이 섞인다). 승격은 새 Worker + 구조화 인계로 한다.
- 요청값(프로필)과 실제 실행값을 구분해 기록한다. 상태 스냅샷에서 실제 model·thinking을 확인할 수 있는지는 [미확인]이다.

## 2. 프로필 대응표 (2026-11-25 `list_profiles` 확인값)

| Paseo 프로필 | provider/model · mode · thinking | 정본 라우팅 항목(host orca) | 일치 여부 |
|---|---|---|---|
| `root-orchestrator` | claude/claude-sonnet-5-5 · auto · high | `roles.root_orchestrator`: Terra high → 대체 Sonnet high | 대체 경로 사용. 사유: Codex에 Paseo 도구 없음(사용자 승인 2026-11-25) |
| `project-coordinator` | claude/claude-sonnet-5-5 · auto · high | `roles.project_coordinator`: Luna high → 대체 Terra high | Orca 호스트 값은 Luna high → Terra high(1.5.0 그대로). **Paseo 호스트 값은 Sonnet high, 대체 없음**(json 1.6.0 반영, 5절 P2). 프로필과 `--host paseo` 결과가 일치한다 |
| `dev-l1-simple` | codex/gpt-6-luna · auto · medium | `levels.1`: Luna medium | 일치 |
| `dev-l2-general` | codex/gpt-6-luna · auto · high | `levels.2`: Luna high → Sonnet high | 일치(대체는 프로필 없음, 필요 시 Sonnet high로 수동 구성) |
| `dev-l3-complex` | claude/claude-sonnet-5-5 · auto · high | `levels.3`: Sonnet high → Terra high | 일치 |
| `l4-critical` | claude/claude-opus-5-5 · auto · high | `levels.4`: Opus high → Sol high | 일치. 프로필 메모의 대체 ID `gpt-6.2-sol`은 1.7.0 고정 ID(`models.sol.id`)와 같다(P5) |
| `l5-last-resort` | claude/claude-fable-5-1 · auto · high | `levels.5`: Fable high → Astra high | 일치. 메모의 `gpt-6.2-astra`는 1.7.0 고정 ID(`models.astra.id`)와 같다(P5). Fable 5-2는 관찰만 했고 채택하지 않았다(`alias_observed`) |
| `review-codex-work` | claude/claude-sonnet-5-5 · **plan** · medium | `code_review_codex`: Sonnet medium(중요 시 `important_review_codex` Sonnet high) | 일치. plan 모드로 읽기 전용 |
| `review-claude-work` | codex/gpt-6.1-terra · auto · high | `code_review_claude`: Terra high → Luna high | 모델 일치. 읽기 전용이 모드로 강제되지 않는다(메모: "Instruct read-only"). `features.plan_mode=true`를 켜는 것을 권장하나(제안 P6, 미적용: `sync`가 `features`를 관리하지 않으므로 사용자가 프로필 설정에 직접 반영) 지침 수준 보호일 뿐 **강제가 아니다**. 읽기 전용 증거는 리뷰 전후 `git status`/diff 무변경 검사(필수). 2.1절 |
| `lookup` | codex/gpt-6-luna · auto · medium | `roles.lookup`: Luna medium, `log_summary`: Luna low | 일치(log_summary는 thinking low로 변경해 생성) |

위 10개는 `paseo_profiles`의 비임시 항목이며 `check`는 JSON 파생값과 실제 프로필이 같다고 보고한다(2026-11-25 실제 `~/.paseo/config.json` 읽기 전용 점검: `drift: false`, 변경 0). 임시(provisional) 항목 3개는 6.1절.

### 2.1 Codex 리뷰어 읽기 전용 (Q3, 2026-11-25 확정)

**시험(2026-11-25, Codex `gpt-6-luna`, modeId `auto`, `features.plan_mode=true`)**
- 1차: 읽기(`ls`, `pwd`)만 실행·성공. 셸 파일 생성(`echo > probe1.txt`)과 편집 도구 파일 생성은 «모드 지침 때문에 시도하지 않음».
- 2차: 오케스트레이터가 임시 폴더 한정 쓰기를 명시 허용했는데도 «Plan 모드 지침이 파일 변경을 금지하므로 시도할 수 없다»며 거부. 폴더는 끝까지 비어 있었다(파일 0개 확인). 응답이 «도구/샌드박스가 막은 것이 아니라 내가 안 한 것»이라고 명시했다.
- 해석: `plan_mode`는 **지침 수준 제한**으로 매우 견고하게 지켜졌다. 그러나 도구·샌드박스가 쓰기를 거부한 것이 아니므로 **도구 수준 강제 여부는 미확인**이며 이 시험으로 강제를 증명할 수 없다. Codex 샌드박스는 workspace-write이고(작업 폴더 밖 `.git` 메타데이터 쓰기 거부 실측, common §2) 읽기 전용 샌드박스 모드는 Paseo가 노출하지 않는다(modes: auto, auto-review, full-access).

**확정 규칙**
1. Codex 리뷰어(`review-claude-work`)는 `features.plan_mode=true`를 켜는 것을 **권장**한다(지침 수준 보호).
2. 그러나 «읽기 전용이 강제된다»고 주장하지 않는다. 읽기 전용의 증거는 **리뷰 전후 대상 worktree의 `git status`/diff가 같다는 확인(무변경 검사)**이며 이 검사는 필수다. 변경이 생기면 리뷰 결과를 무효로 하고 원인과 함께 보고한다(되돌리지 않고 Owner가 판단).
3. 쓰기 차단이 반드시 필요한 중요 리뷰(보안·무결성 등)는 **Claude `plan` 모드 리뷰어**를 쓴다. 계열 교차를 포기하는 대신 모드 설명상 도구 실행이 막힌다. Claude `plan` 모드는 «도구 실행을 막는 모드로 설명됨(Paseo 모드 설명: «Analyze the codebase without executing tools or edits»)»이며 이 세션에서 쓰기 시도로 검증하지는 않았다.
4. `review-claude-work`의 modeId가 `auto`이므로 plan_mode를 켜는 프로필 변경은 **제안 P6**(5절)이며 아직 적용하지 않았다. `features`는 `sync`가 관리하지 않는 필드이므로 사용자가 프로필 설정에 직접 반영해야 한다.
5. 리뷰어는 commit하지 않는다(Codex는 Paseo worktree에서 commit이 막히고 권한 모드를 올려 우회하지 않는다).

세부 작업 유형(`requirements`, `decomposition`, `architecture`, `refactor_design`, `db_design`, `test_design` 등)이 Terra high나 Sonnet high를 기본으로 지정하는 경우, 맞는 프로필이 없으면 Owner가 정본 값으로 `provider`·`thinkingOptionId`를 직접 구성하고 선택 이유를 기록한다. 이를 위해 프로필을 새로 만들거나 바꾸는 것은 사용자 승인 사항이다.

## 3. 선택 절차

1. 우선순위대로 판정: 필수 고위험 전문 경로(`high_risk_types`, LEVEL 4 유형) → 프로젝트·사용자 명시 지정 → 단순 작업 조건(명확한 소범위·자동 검증 가능·저위험을 모두 충족하면 LEVEL 1) → 작업 유형(`task_routes`) → 복잡도 기본값(`levels`).
2. 저장소 checkout이 있으면 라우터를 `--host paseo`로 실행해 판정을 얻는다: `python3 -B -m ai_policy.routing --host paseo --task-type <유형>`(또는 `--role`, `--level`, `--failures`, `--failure-kind`, `--available`). `action`이 `blocked_no_available_model`(종료 40)·`handoff_to_lead`(종료 41)이면 Worker를 만들지 않고 상위 Owner에 보고한다. Paseo 호스트 출력은 `orca_worker_args`를 비우고 `paseo_create_agent`(`provider`=`<tool>/<model>`, `settings.modeId`·`thinkingOptionId`, 리뷰의 `settings.features`)와 `paseo_profile`(2절 프로필 이름)을 준다. `paseo_profile`은 임시(provisional)가 아닌 프로필의 파생값(6.1절)과 라우터 결과의 모델 id·`modeId`·thinking이 모두 같을 때만 이름을 주고, 하나라도 다르면 null이다(예: Terra 수평 단계, 새 캐시 id, plan 모드로 도는 `important_review`, 임시 프로필만 맞는 Astra). 프로필에는 매개변수가 없으므로 Owner가 `paseo_create_agent` 값을 `create_agent`에 복사하거나 프로필의 값을 복사한다. `thinkingOptionId`는 effort 이름을 그대로 쓰며 대상 모델이 그 옵션을 지원하는지는 `inspect_provider`/`list_models`로 확인한다(미확인). 프로필 실제 값이 정책 JSON 파생값과 다르면 JSON이 정본이다(6절 `check`로 확인하고 `sync`로 맞춘다). 사용 불가·승격·처리 결과는 같은 `action` 규약(종료 40·41)을 따른다.
   추가 입력(모든 호스트 공통): `--failed-family claude|codex|both`(쉼표 구분, LEVEL 4에서 실패한 계열. 순서는 무시하며 두 계열을 주면 `both`와 같다. 하나만 주면 LEVEL 5에서 반대 계열 후보를 먼저 쓰고 `l5_opposite_family:<alias>`를 남긴다. 쓸 수 없으면 `l5_opposite_family_unavailable`, `both`·없음은 호스트 기본, 그 밖은 `unknown_failed_family`), `--failed-model <별칭 또는 id>`(LEVEL 4에서 그 모델을 건너뛴다, `excluded_failed_model:<alias>`, 남는 후보가 없으면 `blocked_no_available_model`), `--implementer-family claude|codex`(리뷰 유형에서 리뷰어를 반대 계열로 고른다, 3.1절, 그 밖은 `unknown_implementer_family`). 결과에 `lateral`, `degraded_independence`, `premium_requires_reason`(premium·exceptional 선택이면 true, 차단되면 false)이 항상 들어간다.
   LEVEL 2 수평 단계: 레벨 기준 선택(`--level`·작업 유형)에서 계수 대상 실패가 1회 쌓이면 두 번째이자 마지막 LEVEL 2 시도는 `levels.2.lateral.paseo`(Terra high)로 간다(`lateral: true`, 이유 `lateral_step`, 대체 후보 없음). Terra를 쓸 수 없으면 `lateral_unavailable:terra`로 곧장 LEVEL 3으로 올린다. 역할(`--role`)과 비모델 실패에는 적용하지 않는다. 또한 첫 시도가 실제로 쓴 모델(작업 유형 경로의 첫 항목, 없으면 레벨 값)과 같은 도구의 수평 모델일 때만 적용하고, `cross_family_review.task_types`(리뷰 유형)에는 적용하지 않는다. 적용하지 않는 경우 실패 1회 재시도는 같은 경로를 그대로 다시 쓴다(예: `code_review_codex`는 Sonnet, `diagnose_codex_failure`는 Sonnet, `requirements`는 Sonnet). 이 단계는 Orca·codex 호스트 출력도 바꾼다(Claude 호스트는 수평 항목이 없다). 레벨당 2회 시도이므로 LEVEL 1에서 시작하면 LEVEL 4 전까지 최대 6회, 전체 10회다.
3. 선택된 tool·model·effort를 프로필에 대응시키고, 없으면 직접 구성한다. Codex 모델 ID는 30일 이내 `models_cache.json`에서 계열별로 해석하며, `pinned_fallback`이면 캐시를 갱신한 뒤 다시 확인한다. Paseo가 보여 주는 모델 목록(`list_models`)과 대조한다.
   3.1 교차 계열 리뷰와 쓰기 차단(`--host paseo`): `--implementer-family`를 준 `cross_family_review.task_types`(`review`, `code_review_codex`, `code_review_claude`, `important_review`, `important_review_codex`, `security_review`) 리뷰는 먼저 구현자와 다른 계열 후보를 고른다. 다른 계열을 쓸 수 없으면 일반 리뷰는 같은 계열로 진행하되 `degraded_independence: true`(이유 `degraded_independence`)로 표시하고, `blocking_types`(`security_review`)와 고위험 리뷰는 `blocked_no_independent_reviewer`(종료 40, 상태 보존, Worker 생성 금지)다. 그다음 `review_mode`의 쓰기 차단 검사를 선택된 리뷰어에 적용한다: 쓰기 차단이 필요한 `security_review`에서 선택된 리뷰어가 Codex이면 막는다. 이 조합은 실패 시 닫는(fail-closed) 기본값이며 `security_review`에는 저하 경로를 두지 않는다. `implementer_family`를 준 경우 차단 action은 `blocked_no_independent_reviewer`, 주지 않은 경우(기존 동작)는 `blocked_no_available_model`이며 둘 다 종료 40이다.

   | `security_review` (Paseo) | 사용 가능한 계열 | 결과 |
   |---|---|---|
   | 구현자 codex | Claude 포함 | 실행: Claude `plan` 모드 리뷰어(Sonnet high), `paseo_review.write_block_required: true` |
   | 구현자 codex | Codex만 | 차단. 이유 `independent_reviewer_required`·`review_write_block_requires_claude_plan` 둘 다 기록 |
   | 구현자 claude | Claude만 | 차단. 이유 `independent_reviewer_required` |
   | 구현자 claude | 둘 다 | 차단: Codex는 쓰기 차단 조건에, Claude는 독립성 조건에 걸린다. 이유 두 가지 기록 |
   | 구현자 미지정 | Claude 포함 / Codex만 | 실행(Claude plan) / `blocked_no_available_model`(`review_write_block_requires_claude_plan`) |

   `review_mode.task_types`는 `cross_family_review.task_types`와 같아야 하며 로더가 검증한다(어긋나면 `routing_config_invalid`). 그래서 `important_review`도 Claude `plan` 모드 시작 구성을 받는다. 차단되는 결과의 `paseo_create_agent`·`paseo_profile`은 null이다. Orca·claude·codex 호스트에서는 독립성 검사만 적용하고 쓰기 차단 검사는 없다.
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

## 5. `model-routing.json` 변경 제안과 반영 상태 (1.7.0, 2026-11-25)

정본 `model-routing.json`은 1.7.0이며 변경 이력(`changelog`)을 포함한다. 1.7.0은 `docs/paseo-policy-source`의 1.6.0(P1~P4)과 main의 58037de(번호 없는 1.6.0)를 합치고 P5를 적용한 것이다. 1.6.0과 달리 **Orca·codex 호스트 출력도 바뀐다**(LEVEL 2 수평 단계: 실패 1회 뒤 두 번째 시도가 Luna에서 Terra로 간다). 그 밖에 `failed_family`·`failed_models`·`implementer_family` 입력, `cross_family_review`, `premium_requires_reason`, 모델 id 갱신이 들어갔다.

- **P1 host 추가 — 반영.** `hosts.paseo = {"tools": ["claude","codex"], "orchestrator_tools": ["claude"], "alternatives_key": "paseo_alternatives", "task_routes_key": "task_routes", "default_mode_id": "auto", ...}`. 라우터는 `--host paseo` 출력으로 `paseo_create_agent`·`paseo_profile`·`paseo_review`를 내고 Paseo 호스트에서는 `orca_worker_args`를 비운다. 작업 유형 경로(`task_routes`)는 Orca와 Paseo가 공유한다. 모든 레벨·역할에 `paseo` 항목이 있다(레벨은 Orca 값과 동일).
- **P2 역할 기본값 — 반영(Q7 결정됨).** Paseo 호스트에서 `root_orchestrator`·`project_coordinator`는 Sonnet high이고 대체가 없다(`paseo_alternatives: []`). `orchestrator: true` 역할은 `orchestrator_tools`(Claude)만 후보가 되므로 Codex는 제외되고, 사용할 수 없으면 `blocked_no_available_model`(종료 40)이다. 승격으로 레벨이 올라간 뒤와 수평 단계의 Terra는 Worker로 취급한다. 로더는 오케스트레이터 역할의 프로필이 `orchestrator_tools` 밖의 도구를 쓰면 거부한다. **Orca 호스트의 `project_coordinator` 대체 목록(Terra high)에는 Sonnet high를 추가하지 않았다.**
- **P3 프로필 블록 — 반영·확장.** `paseo_profiles`는 이제 관리 대상 프로필의 정본이다(6.1절 스키마). 1.6.0의 이름 전용 맵을 확장했다.
- **P4 리뷰 mode — 반영.** `review_mode`: claude는 `modeId: plan`(`enforced: null`, 쓰기 시도 검증 안 됨), codex는 `modeId: auto` + `features.plan_mode=true`, `enforced: false`, `evidence: git_status_diff_unchanged`. 대상 유형은 `cross_family_review.task_types`와 같고(`important_review` 추가), `security_review`는 쓰기 차단이 필요한 유형(`write_block_required`)이다. Codex 리뷰어가 선택되면 이유에 `review_write_block_requires_claude_plan`을 남긴다.
- **P5 Codex 고정 ID — 적용(1.7.0).** `sol`은 `gpt-6.2-sol`, `astra`는 `gpt-6.2-astra`(모델 `id`와 `codex_model_families` 양쪽). haiku는 `claude-haiku-5-5`(Paseo 별칭 해석 결과, efforts low~max를 선언하지만 라우트의 effort는 여전히 null이고 `lookup_only`). fable의 `claude-fable-5-2`는 `alias_observed`로 관찰만 기록했고 채택하지 않았다(`adopted: false`, 고정 id는 `claude-fable-5-1`, `access_verified_on`은 5-1 기준 2026-11-06 유지).
- **P6 Codex 리뷰어 프로필의 plan_mode — 미적용.** `review-claude-work` 프로필에 `features.plan_mode=true`를 켜는 변경은 사용자 `~/.paseo/config.json` 반영이 필요하고 `sync`가 `features`를 관리하지 않으므로(결정 D2) 정책 도구가 적용하지 않는다. 라우터 출력의 `paseo_create_agent`는 리뷰의 `settings.features.plan_mode=true`를 담으므로 Owner가 직접 구성할 때는 이미 반영된다. 사용자 설정 반영 후 새 리뷰어 세션에서 plan_mode 적용과 무변경 검사를 첫 사용 시 확인한다.
- **검증 범위(`verified_on` 2026-11-25, JSON `verification_scope`).** 검증됨: Codex 정확 id 4개(`gpt-6.2-sol`, `gpt-6.2-astra`, `gpt-6.1-terra`, `gpt-6-luna`)를 ChatGPT 계정의 Paseo codex로 실행했고, Claude 별칭 opus·haiku·fable이 각각 `claude-opus-5-5`·`claude-haiku-5-5`·`claude-fable-5-2`로 해석됨을 확인했다. 미검증: `claude-haiku-5-5`·`claude-sonnet-5-5`·`claude-fable-5-1`의 정확 id 실행, haiku 5-5의 effort 지원.

## 6. 프로필 정본과 점검·동기화 (`ai_policy.paseo`)

**정본 규칙: `policy/model-routing.json`이 정본이다.** `~/.paseo/config.json`의 `daemon.agentProfiles`는 JSON에서 파생한 값을 반영하는 대상이며, 어긋나면 JSON을 기준으로 고친다(이전 문서의 «Paseo 설정이 정본» 규칙은 폐기). 관리 대상은 `paseo_profiles`의 키뿐이며 그 밖의 프로필·`features`·`name` 등 다른 필드와 파일의 다른 설정은 건드리지 않는다. Paseo 데몬은 `config.json`을 자동으로 다시 읽지 않는다(2026-11-26 실측): `sync`로 바꾼 뒤에는 `paseo daemon reload`를 실행하고(`daemon.agentProfiles`는 재시작 없이 반영되며 출력의 `appliedPaths`로 확인) `list_profiles`로 확인한다. 설정이 스키마에 맞지 않으면 reload가 오류를 내며 데몬은 이전 프로필을 유지하므로, 그때는 `sync --restore <백업>`으로 파일을 되돌린다. reload 전에 앱 UI에서 프로필을 저장하면 이 변경을 덮어쓸 수 있는지는 미확인이다.

### 6.1 `paseo_profiles` 스키마

프로필 id(소문자·숫자·`-`)마다 다음 키를 둘 수 있다(그 밖의 키는 로더가 거부한다).

| 키 | 의미 |
|---|---|
| 선택자 `role` \| `level` \| `task_types` | 최대 하나. `role`은 `roles.<이름>.paseo`, `level`은 `levels.<n>.paseo`에서 값을 가져온다. `task_types`는 `expect`가 필수다 |
| `expect` | `[alias, effort]`(effort는 null 가능). 선택자의 후보(호스트 기본·`paseo_alternatives`·`lateral`·그 유형의 `task_routes` 항목) 중 하나여야 한다 |
| `description` | 프로필 `notes`가 된다 |
| `provisional` | true면 라우터가 이름으로 안내하지 않고, `sync`는 `--include-provisional`일 때만 만든다. 없어도 드리프트가 아니다 |
| `mode_id` | modeId 직접 지정 |

선택자가 없는 프로필은 `provisional: true`이고 `expect`가 있어야 한다. 오케스트레이터 역할의 프로필은 `hosts.paseo.orchestrator_tools`(Claude) 도구만 쓴다. JSON의 중복 키는 거부된다. 위반은 모두 `routing_config_invalid`다. 파생 함수 `paseo_profile_spec(config, id)`가 돌려주는 값은 `provider`(모델의 도구), `model`(항상 정책의 정확한 id, 별칭 아님), `modeId`(`mode_id`, 없으면 그 프로필의 모든 `task_types`가 `review_mode.task_types`일 때 `review_mode[도구].modeId`, 아니면 `hosts.paseo.default_mode_id`), `thinkingOptionId`(effort, null이면 필드를 쓰지 않으며, 그런 프로필에 값이 남아 있으면 `check`가 드리프트로 보고하고 `sync`가 필드를 제거한다. 값이 null인 것은 미설정으로 본다), `notes`, `provisional`이다.

임시 프로필: `scout`(haiku, effort 없음, `plan` 모드, 파일·심볼 정찰), `ui-verify`(Terra high), `l5-alt-astra`(Astra high, LEVEL 5 대체 — LEVEL 4 실패 계열이 Claude일 때). 모두 실제 프로필이 아직 없고 Sol을 기본으로 쓰는 프로필은 없다.

### 6.2 `check` (읽기 전용)

`python3 -B -m ai_policy.paseo check [--config <config.json>] [--policy <model-routing.json>] [--model-catalog <models_cache.json>] [--paseo-models <list_models.json>]`

종료 코드 0 = 드리프트 없음, 1 = 드리프트(관리 프로필의 `provider`/`model`/`modeId`/`thinkingOptionId` 불일치(effort가 null인 프로필에 값이 남은 경우 포함), 비임시 프로필 누락, 같은 id 중복), 2 = 입력 오류(`{"schema":1,"error":"<코드>"}`). `notes_differ`, 임시 프로필 누락(`missing_provisional`), `unmanaged_profiles`, Codex의 `newer_generation_available:<id>`·`catalog_stale_or_missing`, Claude의 `newer_alias_observed`·`--paseo-models`가 주는 `newer_available`은 정보일 뿐 종료 코드에 영향이 없다. 기본 `--config`는 `~/.paseo/config.json`이다. 파일을 쓰지 않고 Paseo를 호출하지 않는다.

### 6.3 `sync`와 `--restore`

`python3 -B -m ai_policy.paseo sync [--config ...] [--policy ...] [--model-catalog ...] [--state-dir <dir>] [--include-provisional] [--overwrite ID[,ID]] [--plan-sha256 <해시>]`

1. **드라이런이 기본이다.** 계획 JSON(`profiles[id].action`, `changes`, `conflicts`, `refusals`, `plan_sha256`)만 출력하고 아무것도 쓰지 않는다. action은 `noop`·`create`·`update`·`conflict`·`refused:pinned_fallback`·`refused:downgrade`·`skip_provisional`이다.
2. **적용은 `--plan-sha256 <드라이런이 출력한 해시>`를 줄 때만.** 해시는 설정 파일 내용·플래그·카탈로그에 따라 바뀌며 하나라도 다르면 `plan_sha256_mismatch`로 거부한다. 쓰기 직전에 대상 파일의 sha256을 다시 확인하고(다르면 `config_changed`) 임시 파일 + `os.replace`로 원자적으로 교체하며, 쓴 뒤 다시 읽어 검증한다(`post_write_verification_failed`). 적용 결과는 `daemon_reload_required: true`와 `paseo daemon reload` 실행·확인 안내(reload가 설정 거부를 보고하면 `--restore`)를 포함한다. 교체 뒤의 검증·상태 저장이 실패하면(`post_write_verification_failed`, `state_save_failed`) 종료 코드 2와 함께 `applied: true`, `backup`(되돌릴 백업 경로), `state_saved: false`를 담은 구조화된 오류를 낸다. 설정 파일은 이미 바뀐 상태이므로 `--restore`로 되돌릴 수 있다(`--restore`도 교체 뒤 검증 실패 시 `applied: true`, `pre_restore_backup`을 낸다).
3. **형식 드리프트 방지.** 파일이 `json.dumps(indent=2, ensure_ascii=False)` + 개행과 바이트 단위로 같지 않으면 쓸 변경이 있을 때 `config_format_drift`로 거부한다(변경이 없으면 오류가 아니다).
4. **백업과 상태.** 적용 전에 원본 바이트를 `<state-dir>/backups/config.<UTC시각>.<sha8>.json`(파일 0600, 디렉터리 0700)에 복사한다. 내용은 출력하지 않는다. 마지막 적용값은 `<state-dir>/state.json`에 기록한다. 적용(`--plan-sha256`)할 때마다 쓴 프로필과 이미 정책과 같은(`noop`) 프로필을 기준선으로 기록하므로(충돌·거부·건너뛴 임시 프로필은 기록하지 않는다), 쓸 변경이 없는 적용도 설정 파일은 건드리지 않고 상태만 저장한다. 상태에는 대상 설정 파일의 절대경로가 들어가며 다른 파일의 상태(또는 경로가 없는 상태)는 `state_config_mismatch`로 거부한다(`--restore` 포함). 기본 `--state-dir`는 저장소 밖의 사용자별 경로 `${XDG_STATE_HOME:-~/.local/state}/ai-policy/paseo-sync/<설정 파일 절대경로 sha256의 앞 8자>`이며(상위 디렉터리도 0700으로 만든다, `XDG_STATE_HOME`이 절대경로가 아니면 무시), `--state-dir`로 바꿀 수 있다. 백업은 설정 파일 전체 사본이라 비밀 값이 들어 있을 수 있으므로 저장소에 두거나 커밋하지 않는다(`.gitignore`에도 `.local-artifacts/`를 넣었다). 상태·백업 디렉터리가 심볼릭 링크이거나 소유자·권한이 맞지 않으면 거부한다.
5. **충돌.** 기존 프로필의 관리 필드 값이 정책 값과 다르고, 그 현재 값이 `sync`가 마지막으로 적용한 값(상태 기록)과도 다르면(사람이 고친 것으로 본다. 기록이 없으면 항상 해당) `conflict`이며 건드리지 않는다. 종료 코드 1. `--overwrite ID[,ID]`로 지정한 관리 프로필은 덮어쓴다(`overwritten: true`). 충돌은 다른 프로필의 적용을 막지 않는다.
6. **거부(`--overwrite`로 해제 불가).** Codex 모델 id는 카탈로그가 오래됐거나 없어 `pinned_fallback`이면 바꾸지 않고(`refused:pinned_fallback`), 같은 계열 안에서 낮은 세대로 되돌리지 않는다(`refused:downgrade`: 같은 Codex 계열(luna·terra·sol·astra)의 낮은 `gpt-N` 세대, 같은 Claude 계열의 낮은 버전). 계열이 바뀌는 변경(예: Terra 6.1 → Luna 6, Sol 6.2 → Terra 6.1)은 세대 비교 대상이 아니므로 거부하지 않는다(사람이 고친 값이면 일반 충돌 규칙을 따른다). 종료 코드 1.
7. **쓰는 범위.** 기존 프로필은 `provider`·`model`·`modeId`·`thinkingOptionId`만 갱신하며 effort가 null인 프로필의 남은 `thinkingOptionId`는 일반 충돌 규칙에 따라 제거한다(`notes`·`name`·`features`·`options`·다른 프로필은 그대로). 없는 프로필은 `id`·`name`(=id)·관리 필드·`notes`로 만든다(`options` 키는 넣지 않는다: Paseo는 `options: null`을 «expected record»로 거부하고 기존 프로필도 이 키가 없다. 2026-11-26 실측). 임시 프로필은 `--include-provisional`일 때만 만든다.
8. **복원.** `sync --restore <백업 경로>`도 드라이런이 기본이며 `--plan-sha256`으로 적용한다. 백업은 `<state-dir>/backups/` 바로 아래의 정규 파일·정해진 이름·내용 해시가 일치하는 것만 받고(경로 이탈·심볼릭 링크·비정규 파일 거부) 교체 전 현재 파일도 백업한다. `--include-provisional`·`--overwrite`와는 함께 쓰지 못한다.

종료 코드: 0 = 성공(드라이런 포함), 1 = 충돌 또는 거부가 있음, 2 = 오류(`config_changed`, `plan_sha256_mismatch`, `config_format_drift`, `state_invalid`, `duplicate_profile_id`, `overwrite_unknown_id` 등).
