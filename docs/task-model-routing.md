# 공통 작업 유형별 모델 라우팅

정본은 `policy/model-routing.json`의 `task_routes`다. Orca와 Paseo가 동일한 후보 순서를 사용하며, 호스트별 도구 가용성·고위험 우선 경로·실패 승격·리뷰 제한은 각각의 라우터와 운영 정책이 결정한다. 이전 설정의 `orca_task_routes`도 기존 호환 경로로 지원한다.

실제 후보와 대체 경로는 `python3 -B -m ai_policy.routing --host <orca|paseo> --task-type <유형>`으로 확인한다. 모델별 역할과 고위험 기준은 [Paseo 라우팅](paseo-model-routing.md)과 [Orca 라우팅](orca-model-routing.md)을 참조한다. 이 표 자체가 접근 가능성이나 모델 품질의 보증은 아니다.

| 유형 | 기본 → 대체 |
| --- | --- |
| `requirements` | sonnet high → terra high |
| `decomposition` | terra high → sonnet high |
| `architecture` | terra high → luna high |
| `task_coordination` | luna medium |
| `simple_edit` | luna medium |
| `feature` | luna high → sonnet high |
| `multi_module` | sonnet high → terra high |
| `refactor_design` | terra high → luna high |
| `refactor_implementation` | sonnet high → terra high |
| `frontend` | luna high → sonnet high |
| `frontend_complex` | sonnet high → terra high |
| `api` | luna high → terra high |
| `db_design` | terra high → sonnet high |
| `bugfix` | luna high → sonnet high |
| `diagnose_codex_failure` | sonnet high |
| `diagnose_claude_failure` | luna high |
| `test_design` | sonnet high → terra high |
| `test_implementation` | luna high → sonnet high |
| `code_review_codex` | sonnet medium |
| `important_review_codex` | sonnet high |
| `code_review_claude` | terra high → luna high |
| `review` | sonnet medium → luna high |
| `security_review` | sonnet high → luna high |
| `release_validation` | luna high → terra high |
| `docs` | luna medium → sonnet medium |
| `log_summary` | luna low |
