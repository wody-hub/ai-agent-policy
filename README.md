# AI Agent Policy

Codex와 Claude Code의 공통 지침, 모델별 역할 배분, 멀티에이전트 운영 전략을 공유하고 관리하는 저장소입니다.

Codex와 Claude Code의 적용 프롬프트를 각각 제공합니다. 문서는 자동 실행되지 않으며, 적용 프롬프트를 해당 도구에 입력하면 로컬 지침과 설정이 변경됩니다.

## 공유 문서

| 도구 | 문서 | 용도 |
| --- | --- | --- |
| Codex | [적용 프롬프트](codex-global-model-routing-prompt.md) | 전역 지침과 기본 모델 설정에 전략 적용 |
| Claude Code | [운영 전략](claude-code-model-routing-strategy.md) | 최신 모델 기준 역할 배분·변경 근거 확인 |
| Claude Code | [적용 프롬프트](claude-code-global-model-routing-prompt.md) | 전역 지침·관련 설정·개인 에이전트 정의에 전략 적용 |

## Codex 사용 방법

1. [공통 모델 운영 전략 적용 프롬프트](codex-global-model-routing-prompt.md)를 엽니다.
2. 문서의 코드 블록 내용을 복사하여 자신의 Codex에 입력합니다.
3. Codex가 실행 환경과 사용 가능한 모델을 확인하고, 기존 파일을 백업한 뒤 전역 지침과 설정을 수정합니다.
4. 새 세션에서 적용 결과를 확인합니다.

기본 역할은 다음과 같습니다. 실제 적용은 계정과 실행 환경에서 지원하는 모델·추론 수준에 따라 달라집니다.

| 역할 | 모델 | 추론 수준 |
| --- | --- | --- |
| 요구사항·통합·최종 검토 | GPT-6.1 Sol | medium |
| 명확한 기능 구현·검증 | GPT-6 Luna | high |
| 단순 조사·정형 변환 | GPT-6 Luna | medium |
| 복잡한 진단·구조 변경 | GPT-6.1 Sol | high / 필요 시 xhigh |
| 예외적인 전문가 판단 | GPT-6 Astra | medium / high |

Claude Code는 필요할 때만 독립 검토에 활용합니다. 작은 작업은 메인이 직접 수행하며, 위임과 병렬 실행은 인계 비용과 통합 위험을 고려해 선택합니다.

## 적용 위치

전역 지침은 유효한 `CODEX_HOME`의 `AGENTS.md`에 반영합니다. 기본 위치는 `~/.codex/AGENTS.md`입니다. 모델과 서브에이전트 기본값은 같은 위치의 `config.toml`에 반영합니다.

Codex는 세션 시작 시 전역 지침을 읽습니다. `AGENTS.override.md`, 프로젝트 지침, 사용자 지정 에이전트 설정 또는 다른 `CODEX_HOME`이 적용에 영향을 줄 수 있으므로 프롬프트에서 이를 확인하도록 요청합니다.

## 업데이트

현재는 문서를 공유하고 각 도구에 적용을 요청하는 방식입니다. 자동 설치·업데이트 스크립트는 포함되어 있지 않습니다.

문서가 변경되면 GitHub의 변경 이력을 확인하고 최신 프롬프트를 다시 적용하세요. 기존 개인 지침과 관련 없는 설정은 보존하고, 변경 전 백업하도록 구성되어 있습니다.

전략의 성능은 실제 업무에서 정확성, 전체 사용량, 완료 시간, 재작업과 통합 결함으로 평가해야 합니다.

## Claude Code 사용 방법

1. [운영 전략](claude-code-model-routing-strategy.md)을 확인합니다.
2. [적용 프롬프트](claude-code-global-model-routing-prompt.md)의 코드 블록을 자신의 Claude Code에 입력합니다.
3. 기존 지침·설정·에이전트 정의를 백업하고 관련 영역만 변경하도록 요청합니다.
4. 새 일반 세션에서 지침 로딩과 실제 모델·추론 설정을 확인합니다.

Claude Code는 Opus 5.5를 메인으로, Sonnet 5.5를 명확한 기능의 실행자로 배치합니다. Haiku는 단순 조회, Fable은 예외적 자문에 사용합니다. 기준일은 2026-10-07이며 실제 모델 접근은 계정과 제공자에 따라 달라집니다.

사용자 지침의 기본 위치는 `~/.claude/CLAUDE.md`, 설정은 `~/.claude/settings.json`, 개인 에이전트는 `~/.claude/agents/`입니다. 실제 설정 디렉터리와 조직·프로젝트 우선순위를 확인한 뒤 적용합니다. 자동 설치·업데이트 스크립트는 현재 제공하지 않습니다.
