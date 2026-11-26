# Paseo 정책

- Paseo 프로젝트 정책이 설치되고 Paseo 업무 context가 확인되면(부모 에이전트의 배정 메시지와 부모 라벨 `paseo.parent-agent-id`가 증거이며, `PASEO_AGENT_ID` 환경 변수·Paseo CLI 설치·Paseo MCP 도구 존재만으로는 Paseo 업무로 판정하지 않는다) 실행 위치·Root/Coordinator/Worker 역할·모델 선택·정산·최소 Task 등록 부트스트랩은 그 정책을 따른다. Paseo 업무에서는 설치된 Paseo 스킬과 해당 프로젝트 지침을 사용한다. 오케스트레이터는 Claude만 맡고 Codex는 Worker로만 쓴다(commit 없이 변경 파일·diff 보고). Worker는 재위임하지 않으며 Owner가 자식 목록을 점검한다.
- Paseo 완료 알림은 턴 종료 신호이지 업무 완료가 아니다. 결과와 검증 근거를 확보하고 Worker가 `running`이 아님을 확인한 뒤 `archive_agent`로 정리한다. relay 켜기·플러그인 설치·`archive_workspace`·schedule 생성·권한 모드 상향·비밀번호/CORS 변경은 Human Gate로 사용자 결정을 받는다.
- 모델 선택·프로필·생명주기 세부는 `~/Project/ETC/ai-agent-policy`의 `docs/paseo-agent-lifecycle.md`, `docs/paseo-model-routing.md`, `policy/paseo-common.md`를 따른다.
