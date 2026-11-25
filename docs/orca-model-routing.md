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

운영 효과는 검증 완료 Task를 기준으로 실패·재시도·리뷰까지 포함해 비교한다. 합성 시험 결과는 초기 배정의 근거이며 비용·성능 서열을 보장하지 않는다.
