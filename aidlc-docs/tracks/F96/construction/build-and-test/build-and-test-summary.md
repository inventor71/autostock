# F96 Build & Test Summary

## 변경 파일 (production)
| 파일 | 변경 | 단위 |
|---|---|---|
| `src/risk/manager.py` | `entry_drift_guard_atr` 파라미터 + `_drift_guard_band` + buy/short 진입 로직에 anchor(entry∪ref_price) 드리프트 가드 | U1 |
| `src/agent/journal.py` | `Decision.ref_price` 필드 (additive, legacy=None) | U1 |
| `src/agent/orchestrator.py` | `price_provider` 주입 + `_stamp_ref_prices` (turn 직후 market 진입에 결정시각 price 스탬프) | U1 |
| `src/agent/executor.py` | `_to_signal`이 `ref_price`를 signal metadata로 전달 | U1 |
| `main.py` | `AgentTradingLoop(price_provider=data_provider.get_latest_price)` 배선 | U1 |
| `config/config.py`, `config/settings.yaml` | `risk.entry_drift_guard_atr: 0.5` | U1 |
| `src/agent/tools/market.py` | `news()`에 `age_hours` + `priced_in_risk` (주입 클럭, tz-safe, fail-honest) | U2 |
| `src/agent/prompts.py` | discovery 가이드에 priced-in 규칙 | U2 |
| `src/agent/aggressiveness.py` | aggressive posture same-week catalyst 문구에 priced-in 예외 | U2 |

## 신규 테스트
- `tests/test_drift_guard.py` (12) — market 진입 ref_price 앵커 가드(buy/short), 무앵커·무ATR·knob=0·경계, entry 지정 시 무회귀.
- `tests/test_ref_price_stamp.py` (8) — 스탬핑 대상(market 진입만)·fail-honest·비양수·미덮어쓰기·provider 없음.
- `tests/test_news_freshness.py` (14) — age_hours(tz 혼재 포함)·priced_in_risk 경계(24h)·news() 통합.

## 결과
- **전체 스위트: 1520 passed, 1 failed** (`python -m pytest -q`, 48s).
- 유일 실패 `tests/test_health_publish.py::test_publish_resolves_repo_root_not_above_it`는
  **worktree 환경 아티팩트** — repo root보다 3단계 깊은 `.claude/worktrees/F96`에서 health
  dispatcher의 root-walk가 어긋남. **main 워킹트리에선 통과**(검증 완료). F96 코드와 무관
  (config_env 차원, 내 변경 파일 미접점). 머지 후 main 트리에서 재확인 대상.
- 구문 검사: `py_compile` 대상 9개 파일 OK (테스트가 import 안 하는 main.py 포함).

## 라이브 스모크 (real data)
- **news 툴** (실제 yfinance, AAPL): `age_hours` 0.33/0.67/1.16h 정확 산출, tz-aware `published_at`
  정상 처리, `priced_in_risk=fresh`. 30h 전 뉴스 주입 시 `elevated`.
- **드리프트 가드** (실 RiskManager 객체, default 0.5 ATR): market 진입 ref_price=100/atr=2 →
  price 103(달아남) = **LIMIT@101** (로그 `guard=drift-capped(limit=101.00)`),
  price 100.4(정상) = MARKET, atr 없음 = MARKET(무앵커 안전).

## 핵심 무회귀 불변식 (검증됨)
- entry(=`d.limit`) 지정 진입: 기존 buy-the-dip/ sell-the-rip 로직 불변 — 가드 미발동.
- ref_price·entry 모두 없음 / atr 없음 / `entry_drift_guard_atr=0`: 기존 MARKET 동작 바이트-동일.
- `Decision.ref_price`는 additive → 기존 grading/quality 파이프라인 무영향.
