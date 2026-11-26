# Paseo 정책

- Paseo 업무가 확인되면 설치된 Paseo 스킬과 해당 프로젝트 지침을 사용한다.
- Paseo 프로젝트 정책이 설치되고 Paseo 업무 context가 확인되면(부모 에이전트의 배정 메시지와 부모 라벨 `paseo.parent-agent-id`가 증거이며, `PASEO_AGENT_ID` 환경 변수·Paseo CLI 설치·Paseo MCP 도구 존재만으로는 Paseo 업무로 판정하지 않는다) 실행 위치·Root/Coordinator/Worker 역할·모델 선택·정산·최소 Task 등록 부트스트랩은 그 정책을 따른다. 오케스트레이터는 Paseo 도구가 있는 Claude(Sonnet high)만 맡고 Codex는 Worker로만 쓴다. Codex Worker는 Paseo worktree에서 commit하지 않고 변경 파일·diff를 보고하며 commit은 Claude Worker 또는 Owner가 한다. Worker는 재위임하지 않으며 Owner(부모 에이전트)가 자식 목록을 점검한다.
- Paseo 모델 선택은 로컬 정본 라우터 `--host paseo`의 `paseo_create_agent`(provider·modeId·thinkingOptionId)와 `paseo_profile`을 시작 구성으로 삼고 `create_agent`에 복사한다. 프로필은 시작 구성일 뿐 라우팅·시도 횟수·승격·동시 실행 한도는 Owner가 판정한다. 리뷰어는 Claude `plan` 모드이거나, Codex는 `plan_mode` 권장 + 리뷰 전후 `git status`·diff 무변경 검사를 필수로 하며 읽기 전용이 강제된다고 주장하지 않는다. 요청값과 확인한 실행값을 구분해 기록한다.
- Paseo 완료 알림은 턴 종료 신호이지 업무 완료가 아니다. 수락 응답은 시작의 증거가 아니다. 결과와 검증 근거를 확보하고 Worker가 `running`이 아님을 확인한 뒤 `archive_agent`로 정리한다. relay 켜기·플러그인 설치·`archive_workspace`·schedule 생성·권한 모드 상향·비밀번호/CORS 변경은 Human Gate로 사용자 결정을 받으며 Paseo 설정을 임의로 넓히지 않는다.
- 세부 규칙은 `~/Project/ETC/ai-agent-policy/docs/paseo-agent-lifecycle.md`, `~/Project/ETC/ai-agent-policy/docs/paseo-model-routing.md`, `~/Project/ETC/ai-agent-policy/policy/paseo-common.md`를 따른다.
- Paseo 프로필 값은 `policy/model-routing.json`의 `paseo_profiles`가 정본이며 `python3 -B -m ai_policy.paseo sync` 실행 후 `paseo daemon reload`로 적용한다.
