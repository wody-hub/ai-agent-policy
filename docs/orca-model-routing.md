> **보관(병행기, 2026-11-25).** 조율 도구가 Orca에서 Paseo로 전환되었습니다. 이 문서는 병행기 동안 **기존 Orca가 소유한 진행 중 Run·worktree를 마무리**할 때만 사용하며, 새 Task는 [Paseo 설치 지시서](../paseo-project-setup.md)를 따릅니다. 삭제하지 않으며, 모든 Orca Run의 정산·Dispatch release를 확인한 뒤 «보관»으로 확정합니다([이전 설계](paseo-migration-design.md) Q1).

# Orca 작업 유형별 모델 라우팅

공통 Orca 기본값은 `policy/model-routing.json`에 둔다. 필수 고위험 전문 경로, 프로젝트·사용자 지정, 단순 조건, 유형, 복잡도 순으로 판정한다. 선택 결과는 새 세션의 배정 후보이며 진행 중인 세션의 모델을 바꾸지 않는다. 기존 역할, 리뷰와 완료 게이트를 적용한다.

| 유형 | 라우터 선택자 | 기본 → 대체 |
|---|---|---|
| 루트 | `--role root_orchestrator` | Terra high → Sonnet high |
| 요구사항 | `requirements` | Sonnet high → Terra high |
| 분해·의존성 | `decomposition` | Terra high → Sonnet high |
| 아키텍처 | `architecture` | Terra high → Luna high |
| 하위 Controller | `--role project_coordinator` | Luna high → Terra high |
| 배분·진행 판단 | `task_coordination` | Luna medium, 판단 복잡도 증가 시 일반 경로 |
| 단순 수정 | `simple_edit` | Luna medium, 단순 조건을 벗어나면 일반 경로 |
| 일반 기능 | `feature` | Luna high → Sonnet high |
| 복잡 구현 | `multi_module` | Sonnet high → Terra high |
| 대규모 리팩터링 | `refactor_design` / `refactor_implementation` | Terra high → Luna high / Sonnet high → Terra high |
| 프론트엔드 | `frontend` / `frontend_complex` | Luna high → Sonnet high / Sonnet high → Terra high |
| 백엔드 | `api` / 복잡하면 `multi_module` | Luna high → Terra high / Sonnet high → Terra high |
| DB 일반 설계·최적화 | `db_design` | Terra high → Sonnet high |
| 디버깅 | `bugfix` | Luna high → Sonnet high |
| 반복 판단 실패 독립 분석 | `diagnose_codex_failure` / `diagnose_claude_failure` | Sonnet high / Luna high |
| 테스트 설계 | `test_design` | Sonnet high → Terra high |
| 테스트 구현 | `test_implementation` | Luna high → Sonnet high |
| Codex 구현 리뷰 | `code_review_codex` / `important_review_codex` | Sonnet medium / Sonnet high |
| Claude 구현 리뷰 | `code_review_claude` | Terra high → Luna high |
| 보안·정합성 리뷰 | `security_review` / 고위험 `security`, `data_integrity` 등 | Sonnet high → Luna high / Opus high → Sol high |
| 통합·릴리스 결과 해석 | `release_validation` | 자동 검증 우선, Luna high → Terra high |
| 문서·이력 | `docs` | Luna medium → Sonnet medium |
| 상태·로그 | `log_summary` | Orca 조회 우선, 요약 Luna low, 복잡하면 Luna medium |

역할 플래그가 표시된 행 이외에는 `python3 -B -m ai_policy.routing --host orca --task-type <선택자>`를 쓴다. 복잡도를 재분류할 때는 적합한 세부 유형 또는 `--level <수준>`을 사용한다. 유형 기본값과 다른 명시 레벨은 해당 레벨 경로를 선택한다. 기존 고위험 유형은 레벨보다 우선한다.

리뷰어는 구현과 다른 도구 또는 독립 실행 컨텍스트를 사용한다. 교차 후보가 막히면 기존 프로젝트 규칙이 허용하는 별도 컨텍스트를 확인한다. 실패 분석에는 실제 원인과 시도 횟수를 넘기고, 환경·권한·정책 설치 누락은 모델 승격으로 처리하지 않는다. 사용 가능 후보와 실제 모델·effort를 확인하며 차단·인계 결과에서는 Worker를 띄우지 않는다.

## 라우팅 CLI 입력과 결과 필드

`python3 -B -m ai_policy.routing --host <orca|claude|codex|paseo>` 에 다음 선택 입력을 더할 수 있다.

| 입력 | 값 | 효과 |
|---|---|---|
| `--failed-family` | `claude` / `codex` / `both` (쉼표 구분) | LEVEL 4에서 실패한 계열(순서는 무시, 두 계열이면 `both`와 같다). 하나만 지정하면 LEVEL 5 후보 중 반대 계열을 우선한다(`l5_opposite_family:<alias>`). `both`면 호스트 기본 후보를 유지한다. 그 밖의 값은 `unknown_failed_family`. |
| `--failed-model` | 별칭 또는 id (쉼표 구분) | LEVEL 4에서 이미 실패한 모델을 후보에서 제외한다(`excluded_failed_model:<alias>`). 남는 후보가 없으면 `blocked_no_available_model`. |
| `--implementer-family` | `claude` / `codex` | 교차 계열 리뷰 유형(`cross_family_review.task_types`)에서 리뷰어를 구현자와 다른 계열로 고른다. 그 밖의 값은 `unknown_implementer_family`. |

결과 JSON의 추가 필드는 다음과 같다.

- `lateral`: LEVEL 2 수평 단계(Terra)가 선택되면 `true`.
- `premium_requires_reason`: 선택 모델이 premium·exceptional 등급이고 `limits.premium_requires_reason`이 켜져 있으면 `true`. 사유 없이 쓰지 않는다.
- `degraded_independence`: 반대 계열 리뷰어가 없어 같은 계열 리뷰어로 진행하면 `true`(`reasons`에 `degraded_independence`).
- `reasons` 추가 값: `lateral_step`, `lateral_unavailable:<alias>`, `l5_opposite_family:<alias>`, `l5_opposite_family_unavailable`, `excluded_failed_model:<alias>`, `degraded_independence`, `independent_reviewer_required`.
- `action`: 보안 리뷰(`cross_family_review.blocking_types`)와 고위험 리뷰에 반대 계열 리뷰어가 없으면 `blocked_no_independent_reviewer`, 종료 코드 40(`blocked_no_available_model`과 같다). 일반 리뷰는 막지 않고 `degraded_independence`로 표시한다. 이 결과에서는 Worker를 띄우지 않는다. `--host paseo`에서는 여기에 쓰기 차단 검사가 더해진다([Paseo 모델 라우팅](paseo-model-routing.md) 3.1절).

## LEVEL 2 수평 단계와 시도 횟수

레벨당 계수 대상 실패는 2회까지 시도한다(`reasoning_failures_before_escalation`=2). LEVEL 2에서 실패가 1회 쌓이면 두 번째이자 마지막 시도는 `levels.2.lateral`의 표준 등급 모델(Terra high)로 보낸다. 이 단계는 대체 후보를 쓰지 않으며 premium 모델은 허용하지 않는다. Terra를 쓸 수 없으면 `lateral_unavailable:terra`와 함께 LEVEL 3으로 올린다. 실패 2회가 되면 LEVEL 3으로 승격한다. 따라서 LEVEL 2 시도는 2회, LEVEL 1에서 시작하면 LEVEL 4 전까지 최대 6회(레벨당 2회)다. 수평 단계는 레벨 기준 선택(`--level`/유형)에만 적용되고 역할(`--role`)에는 적용되지 않는다. 첫 시도가 실제로 쓴 모델(작업 유형 경로의 첫 항목, 없으면 레벨 값)과 같은 도구일 때만 적용하며 교차 계열 리뷰 유형(`cross_family_review.task_types`)에는 적용하지 않는다(그 경우 같은 경로를 다시 쓴다). 환경·권한 등 비모델 실패는 승격하지 않는다. 이 단계는 모델 라우팅 1.7.0부터 Orca·codex·paseo 호스트 출력을 바꾼다(1.5.0·1.6.0에서는 같은 모델을 한 번 더 시도했다). Claude 호스트에는 수평 항목이 없어 그대로다.

## LEVEL 5 반대 계열 규칙

LEVEL 5는 LEVEL 4가 같은 근본 원인에서 두 번 실패한 뒤에만 도달한다. `--failed-family`로 한 계열만 넘기면 반대 계열 후보(Claude 실패 → Astra, Codex 실패 → Fable)를 앞세운다. 이는 선호 규칙이며, 반대 계열을 쓸 수 없으면 `l5_opposite_family_unavailable`을 남기고 기존 후보 순서로 진행한다. LEVEL 5에서 다시 실패하면 `handoff_to_lead`다.

## paseo 호스트와 `paseo_profiles`

`hosts.paseo`는 Paseo가 관리하는 에이전트 프로필(`daemon.agentProfiles`)용 호스트이며 도구는 claude·codex다(오케스트레이터 역할은 claude만). 정책이 관리하는 프로필의 정본은 `policy/model-routing.json`의 `paseo_profiles`(13개, 그중 `scout`·`ui-verify`·`l5-alt-astra`는 임시)이고, 스키마(선택자·`expect`·`description`·`provisional`·`mode_id`와 파생 필드), `ai_policy.paseo check`(읽기 전용 드리프트 점검), `sync`와 `--restore`(드라이런 기본, `--plan-sha256`으로 적용, 백업·충돌·거부 규칙)는 [Paseo 모델 라우팅](paseo-model-routing.md) 6절이 설명한다. 이 문서의 Orca·claude·codex 호스트에는 영향이 없다. `ai_policy/__main__.py`는 설치 번들이 해시로 고정하므로 `paseo`는 `python -m ai_policy` 서브커맨드로 연결하지 않았다.

운영 효과는 검증 완료 Task를 기준으로 실패·재시도·리뷰까지 포함해 비교한다. 합성 시험 결과는 초기 배정의 근거이며 비용·성능 서열을 보장하지 않는다.
