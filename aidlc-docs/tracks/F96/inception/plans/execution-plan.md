# F96 Execution Plan

## Workflow 단계 결정 (adaptive)
| Stage | 결정 | 근거 |
|---|---|---|
| Workspace Detection | ✅ done | brownfield, 코드 심층 분석 완료 |
| Reverse Engineering | SKIP | 대상 코드 이미 분석(executor/risk/market/prompts) |
| Requirements Analysis | ✅ done | Standard, UAQ 4문항 확정 |
| User Stories | SKIP | 단일 운영자, 내부 실행 로직; 시나리오 requirements에 명료 |
| Workflow Planning | ✅ (this doc) | — |
| Application Design | ✅ done (경량) | 기존 컴포넌트 내부 확장, 계약만 고정 |
| Units Generation | SKIP | 독립 소규모 2단위, 별도 분해 불필요 |
| Construction (Code Gen) | EXECUTE | U1, U2 |
| Build & Test | EXECUTE | 단위테스트 + 회귀 + 라이브 스모크 |

## Construction 단위
- **U1 Execution drift guard** — `risk/manager.py`(+`__init__`, `_build_bracket_buy`,
  `_build_bracket_short`), `config/settings.yaml`, RiskConfig 모델, `main.py:_build_risk_manager`.
  Functional Design SKIP(로직 requirements/design에 확정), 테스트 동반.
- **U2 News freshness** — `agent/tools/market.py::news`, `agent/prompts.py`,
  `agent/aggressiveness.py`. 테스트 동반.

## 실행 방식
설계 승인 후 U1→U2 코드+테스트를 **자율 진행**(사용자 preference), 각 단위 완료 시 요약.
Build & Test 그린이면 `merge-awaiting` 표기 + post-merge-guide 작성 후 머지 게이트에서 정지.

## 회귀 안전
- 임계 미달/무앵커/atr 결측 → 기존 동작 바이트-동일 (핵심 불변식).
- 기존 `tests/` risk·executor·market 스위트 그린 유지가 수용 기준.
