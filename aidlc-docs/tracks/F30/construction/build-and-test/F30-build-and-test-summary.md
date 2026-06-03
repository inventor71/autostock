# F30 — Build & Test Summary (KIS 한국주식 브로커 + 동적 universe)

> Brownfield. 기존 pytest 스위트·검증 하네스 재사용. 코드는 `feat/F30`(7커밋 b0024d0→5b5d9cc).
> 단위/통합은 네트워크 비의존(모킹), 라이브는 모의계좌 read-only로 검증됨.

## 1. Build / 환경
```bash
# worktree 부트스트랩(있으면 재사용) — main .env symlink + venv 안내
scripts/worktree-setup.sh F30 --py
# 의존성: KIS SDK 핀이 pyproject에 추가됨(python-kis==2.1.6, import pykis)
<venv>/bin/pip install -e .        # 또는 pip install python-kis==2.1.6
```
**환경변수**(메인 `.env`, gitignored): `KIS_PAPER_API_KEY` / `KIS_PAPER_API_SECRET` / `KIS_PAPER_ACCOUNT`("CANO-PRDT"). 실전 미러 `KIS_LIVE_*`(미구현). `config/settings.yaml`의 `universe.market: kr` + `broker.name: kis`로 KIS 경로 선택.

## 2. Unit + Integration 테스트 (네트워크 비의존)
```bash
<venv>/bin/python -m pytest -q                      # 전체: 620 passed
# F30 신규만:
<venv>/bin/python -m pytest -q \
  tests/test_kis_pricing.py tests/test_kis_broker.py tests/test_kis_provider.py \
  tests/test_universe_provider.py tests/test_kis_integration.py tests/test_executor_protection.py
```
| 파일 | 커버리지 |
|---|---|
| `test_kis_pricing.py` (7, PBT) | round_to_tick 멱등/출력tier배수/단조/within-tick, floor_qty |
| `test_kis_broker.py` (16) | 주문매핑·정수수량·OCO arm·**BRACKET 지연-arm/PENDING_ENTRY 상태기계**·reconcile·get_protective_stops·**get_order_status(ccld)**·저널 round-trip |
| `test_kis_provider.py` (6) | get_bars DataFrame/limit/empty·분봉 폴백·get_latest_price |
| `test_universe_provider.py` (7) | base∪theme/dedup/fallback/fail-closed/캐시/KR 파싱 |
| `test_kis_integration.py` (4) | `--broker kis` 팩토리·client 공유·KST 스케줄·kis_reconcile job |
| `test_executor_protection.py` (4) | **protected_symbols STOP-leg(MED-3)**·**check_stop_loss stop_overrides(HIGH-2)** |

**Critic 커버리지**: HIGH-1(체결확인/TP 사이징), HIGH-2(에이전트 stop_price 손절), HIGH-3(reconcile 레이스), HIGH-4(토큰충돌)·MED-3(protected) 모두 회귀 테스트 보유.

## 3. Lint / 정적검사
```bash
<venv>/bin/python -m py_compile <F30 파일들>       # 구문 — F30 전 파일 OK (확인됨)
<venv>/bin/python -c "import main"                # import 그래프 무결성 (확인됨)
<venv>/bin/ruff check src/ tests/ main.py         # 린트(dev extra: pip install -e '.[dev]' 후)
```
(현재 venv엔 ruff 미설치 — dev extras 설치 후 실행. 전체 스위트가 모든 F30 모듈을 import하므로 import 무결성은 620 통과로 확인됨.)

## 4. 라이브 검증 (모의계좌)
- **완료(read-only, 주문 없음)**: 인증 OK / `get_portfolio_state` cash·equity=50,000,000(모의 시드) / `get_latest_price(005930)`=360,500 / 일봉 5개 OHLCV / KOSPI200 시총랭킹 실데이터.
- **대기(주문 placement)**: KIS 모의는 **평일 09:00–15:30 KST 세션**에만 주문 접수("모의투자 영업일이 아닙니다" 40100000). 장시간에 다음을 권장:
  ```
  # 비마켓터블 지정가 1주 → 미체결 rest 확인 → 취소 (안전)
  KisPaperBroker.submit_order(LIMIT, 현재가 대비 먼 가격) → get_open_orders → cancel_order
  ```
  실호출 검증 후 라이브 BRACKET(지연-arm) 1회 점검.

## 5. Known follow-ups (비차단)
- ~~① KR 랭킹 페이징/KOSDAQ~~ **처리됨(2026-06-03)**: KOSDAQ 정상, 랭킹 EP는 30/시장 고정(페이징 없음) → 동적=top-30×2≈60 liquid, `_min_base` 수정으로 동적 채택.
- ② 모의 **장시간 주문 placement** 라이브 검증(위 4절 절차).
- ~~③ KRX 공휴일 캘린더~~ **처리됨(2026-06-03)**: `is_market_open`이 chk-holiday(opnd_yn) 일캐시 조회로 공휴일 차단(fail-open).

## 6. 회귀/안전
- 기존 US(Alpaca) 경로 무회귀: 전체 620 passed, `protected_symbols` STOP-leg 변경이 Alpaca 보호 유지(critic verified). `trading.symbols` 제거 후 backtest/CLI/collector/tools 전부 `resolve_universe` 재배선 — 그린.
- 모의 안전: 모든 라이브는 모의 도메인(openapivts) + 모의키. 실전 경로는 guarded NotImplementedError.
