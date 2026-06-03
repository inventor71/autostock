# Code Generation Plan — F30 (U1 kis-broker + U2 universe-provider)

> **Single source of truth for F30 Code Generation.** Brownfield — 기존 구조 사용.
> **Worktree gate**: 모든 코드는 `.claude/worktrees/F30`(branch `feat/F30`)에서 생성. (docs는 main.)
> 설계 출처: `construction/{kis-broker,universe-provider}/{functional-design,nfr-requirements}/`,
> `inception/application-design/`.

## 검증 이월 항목 (생성 중 실제 확인 — 막히면 사용자 게이트)
- KIS SDK import 경로(`kis_auth` vs `pykis`) + 모의 인증(`svr="vps"`) 호출 시그니처
- KR ETF 구성종목 tr_id (미가용 시 시총 top-N 폴백)
- US S&P100 `read_html` 소스 URL/표 구조
- KIS 모의 rate limit 정확값 (보수적 2/s 기본)
- KIS 자격증명: `KIS_PAPER_{APP_KEY,APP_SECRET,ACCOUNT_NO}` env (사용자 발급 — Q4=A)

---

## Critic 반영 (2026-06-03 적대적 검토 — 코드로 교차검증 완료)
- **HIGH-1 reconcile 무거처**: standalone(steering 없음)엔 초단위 job이 없음(`agent.py:313` 모든 seconds-job이 steering-gated). → emulated OCO reconcile + held∪open 가격피드를 **steering 무관 always-on seconds job**으로 신규 등록(Phase 4.3a). FD의 "기존 5초 job 합승"은 폐기.
- **HIGH-2 재시작 복원**: `OpenOrder`(`models.py:94-104`)에 group 정보 없음 → OcoGroup을 **저널 파일 영속화 + 기동 시 rehydrate**(사용자 결정). Phase 1.2a.
- **MED-3 보호 커버리지**: `executor.protected_symbols()`(`executor.py:302`)가 open order 1개라도 있으면 protected → SL 거부/취소 시 TP만 남아도 무방비. → protected 판정을 **STOP leg 존재** 기준으로(Alpaca 원자 OCO도 안전). SL arm 실패 시 그룹 전체 실패(TP 취소)로 polled 백업 재engage. Phase 4.1a.
- **MED-4 universe 이관**: `trading.symbols` 읽는 곳 = `main.py:135/305/354/455`, `intraday_collector.py:168`, `agent/tools/__main__.py:35`. → **전부 provider로 재배선**(사용자 결정: 기존 유지 불필요). Phase 3/4 확장.
- **MED-5 cancel stall**: `_cancel_and_wait`(`executor.py:277`) 최대 6초 폴링 → **broker-tunable**(KIS 동기 취소면 짧게/0). Phase 4.1b.
- **LOW-6 tick 멱등**: `round_to_tick` tier를 **출력 기준 재snap**, PBT 불변식은 출력 tier 기준 명시. Phase 1.2/5.2.
- **LOW-7 halt fail-open**: `_update_market_halt`(`executor.py:299`) 예외 삼킴=fail-open. KIS 경로는 로그 WARNING 승격 + 동작(fail-open 유지) 문서화. Phase 4.1.

## Phase 0 — Worktree & Dependency
- [x] 0.1 worktree 확인(`.claude/worktrees/F30`, 이미 생성됨) — 이후 모든 편집 여기서
- [x] 0.2 `pyproject.toml`: KIS SDK git dependency 추가(커밋 핀, SECURITY-10). pandas/yfinance/hypothesis는 기존
- [x] 0.3 `config/config.py` Settings: kis_paper_api_key/secret/account + kis_live_* 필드 추가(로드 검증). `.env`/Settings: `KIS_PAPER_*`/`KIS_LIVE_*` 필드 추가(pydantic Settings, 하드코딩 금지)

## Phase 1 — BaseBroker 속성 + KisBroker (U1)
- [x] 1.1 `src/execution/base.py`: `halt_reference_symbol: str = "SPY"` 클래스 속성 추가(기본값, 기존 브로커 무변경)
- [x] 1.2 `src/execution/brokers/kis_broker.py` — KisBroker(ABC)+KisPaperBroker 구현(아래). 단위 17 passed + 라이브 read-only(auth/balance) 검증. real `_arm_stop`만 abstract(후속) 신규: `KisBroker(BaseBroker)`
  - [x] 생성자: SDK 초기화 + 모의/실전 auth, HTTP timeout 주입, `halt_reference_symbol="069500"`
  - [x] `_ensure_token()` lazy 갱신(>23h), `_throttle()` token-bucket + backoff
  - [x] `round_to_tick(price)` (BR-2 tick 표), `_to_int_qty()` (BR-3 floor)
  - [x] `submit_order`: MARKET/LIMIT/STOP 매핑(BR-1) + BRACKET/OCO emulated 분해
  - [x] `_OcoGroup` 상태기계 + `reconcile_oco()` (§3, BR-5)
  - [x] **(1.2a, HIGH-2)** OcoGroup 저널 영속화: `workspace/kis_oco_groups.json` write-through, 생성자에서 rehydrate(거래소 `get_open_orders`로 잔존 leg 대조 후 stale 그룹 정리)
  - [x] **(LOW-6)** `round_to_tick`: tier를 출력값 기준으로 재snap(경계 교차 시 고정점), 멱등·tick배수(출력 tier)·단조 보장
  - [x] 조회(get_order_status는 PoC best-effort): `get_position`/`get_all_positions`(페이징)/`get_portfolio_state`/`get_order_status`/`get_open_orders`
  - [x] `cancel_order`/`close_position`(시장가, BR-7)/`get_fills`/`get_latest_prices`(보유∪open)
  - [~] `is_market_open`(KST, fail-closed)/`record_trade_ledger`/`replace_order`
  - [x] 에러 매핑 → `BrokerError`(BR-9), 시크릿 로그 차단(SECURITY-03/12)

## Phase 2 — KisDataProvider (U1)
- [x] 2.1 `src/data/providers/kis_provider.py` — KisDataProvider(get_bars 일/주/월 FHKST03010100, get_latest_price FHKST01010100). 단위 6 + **라이브: 모의 도메인 시세 서빙 확인(price=360,500 + 일봉 5개 OHLCV)** 신규: `KisDataProvider(BaseDataProvider)`
  - [x] `get_bars`(일/분봉 tr_id 매핑 → OHLCV DataFrame), `get_latest_price`
  - [x] HTTP timeout, rate-limit(토큰도 throttle 통과 수정), 토큰 공유(client 주입)(또는 자체 lazy)

## Phase 3 — Universe Provider (U2)
- [x] 3.1 `src/universe/base.py` — BaseUniverseProvider(get_symbols base∪theme, 1d 캐시, 스냅샷 fallback, UniverseError). 단위 7 신규: `BaseUniverseProvider`(get_symbols=base∪theme, 1일 캐시, 스냅샷 fallback, `UniverseError`)
- [x] 3.2 `src/universe/kr_provider.py` `KRUniverseProvider` — 시총 상위(market_cap FHPST01740000) KOSPI(2001)+KOSDAQ(1001). **follow-up 처리(2026-06-03)**: 라이브 재확인 — KOSDAQ 정상(앞 0은 rate-limit 아티팩트), 모든 시장 **페이지당 30 고정(EP 페이징 미지원)** → 동적 base = top-30×2≈60 liquid로 현실화, `_min_base`를 30으로 낮춰 **동적이 실제 채택**(기존 87이라 항상 스냅샷이던 버그 수정). 스냅샷은 오프라인 fallback.
- [x] 3.3 `src/universe/us_provider.py` — USUniverseProvider(S- [ ] 3.3 `src/universe/us_provider.py`P100 read_html + yfinance 선택랭킹). 단위(mock) 신규: `USUniverseProvider`(S&P100 read_html + yfinance marketCap top_n)
- [x] 3.4 `config/universe/{kr,us}_base.json` 스냅샷 seed(US=기존 131 symbols, KR=30 major) 스냅샷 seed — **US seed = 제거 전 trading.symbols 값을 먼저 캡처**, **KR seed = 비어있지 않은 커밋 시드**(첫 실행 오프라인 UniverseError 방지)
- [x] 3.5 `config/settings.yaml`+`config/config.py`: `universe.*` 구조 추가(market/top_n/enabled_themes/themes kr·us), `trading.symbols` 필드/기본값(config.py:40) **제거**

## Phase 4 — 통합 (수정 컴포넌트)
- [x] 4.1 `src/agent/executor.py`: 서킷브레이커 `broker.halt_reference_symbol` 사용(하드코딩 "SPY" 제거); **(LOW-7)** halt feed 예외 시 WARNING 로그 + fail-open 동작 주석 명시
- [x] **4.1a (MED-3)** [executor 측: protected STOP-leg 완료; KisBroker 측 SL-arm 실패→그룹실패는 KisBroker 구현 시] `executor.protected_symbols()`: open order 존재가 아니라 **STOP 종류 leg 존재**로 protected 판정(Alpaca 원자 OCO도 STOP leg 보유 → 안전). KisBroker emulated arm에서 SL 거부 시 그룹 실패(TP 취소)로 polled 백업 재engage
- [x] **4.1b (MED-5)** `_cancel_and_wait`: timeout/interval을 broker 속성으로(예: `broker.cancel_settle_wait`); KIS 동기 취소면 0/짧게
- [x] 4.2 `src/trading/scheduler.py`: `add_market_open_job`/`add_market_close_job` timezone/hour/minute 파라미터화(US 기본 하위호환)
- [x] 4.3 `src/trading/modes/agent.py` — broker.market_schedule 기반 KST 스케줄(research 08:00/open 09:00/close 15:20): KIS 브로커/데이터/스케줄(KST) 주입 + universe provider 연동
- [x] **4.3a (HIGH-1)** always-on `kis_reconcile` seconds-job(steering 무관) + `_oco_reconcile_tick` standalone reconcile job: steering 무관 **always-on** `add_seconds_job(self._kis_reconcile_tick, N, "kis_reconcile")` 등록 — `broker.reconcile_oco()` + held∪open 가격피드. (steering 있을 때도 별개로 보장.) KIS 경로에서만 등록
- [x] 4.4 `create_broker`/`create_data_provider` market-aware(broker.name=kis→KisPaperBroker+KisDataProvider, client 공유로 토큰 1/분 회피), run_agent/paper 순서 교체: `--broker kis` 경로(엔진/CLI/팩토리)에서 KisBroker+KisDataProvider+KRUniverseProvider 구성
- [x] **(MED-4) universe 주입점 전면 재배선** — resolve_universe 팩토리, 6곳 교체, trading.symbols 제거. **607 passed** — 다음 **모든** 호출부를 provider로 교체:
  - [x] `main.py`(124/294/343) ← resolve_universe(backtest), `main.py:305`, `main.py:354`(agent) universe ← provider.get_symbols()
  - [x] `main.py` `--symbols` → settings.universe override `--symbols` override → provider 결과 override 의미 정의(임시 StaticUniverseProvider 또는 provider 필터)
  - [x] `intraday_collector.py` ← resolve_universe ← provider
  - [x] `agent/tools/__main__.py` ← resolve_universe `_universe()` ← provider
  - [x] engine/orchestrator universe ← (main이 주입)/`orchestrator` universe ← provider

## Phase 5 — 테스트
- [x] 5.1 `tests/test_kis_broker.py`(10) — 매핑/OCO/청산/파싱/abstract: 주문유형 매핑·OCO 상태기계·청산·에러(모킹)
- [x] 5.2 PBT(Hypothesis): `round_to_tick`(멱등/배수/단조), qty floor 불변식, 매핑 round-trip
- [x] 5.3 `tests/test_universe_provider.py`(7) — 합성/dedup/fallback/fail-closed/캐시/KR파싱: get_symbols 합성/dedup/fallback + PBT(dedup 멱등, normalize 멱등)
- [x] 5.4 (full suite 607 회귀) scheduler timezone / executor halt-ref 회귀 테스트
- [x] 5.5 **(MED-3)** (test_executor_protection) protected_symbols STOP-leg protected_symbols: TP만 남았을 때 미보호 판정 + SL 거부 시 그룹 실패 테스트
- [x] 5.6 **(HIGH-2)** OcoGroup 저널 round-trip 테스트 OcoGroup 저널 영속화 round-trip + 재시작 rehydrate(거래소 leg 대조) 테스트
- [x] 5.7 **(HIGH-1)** (test_kis_integration) standalone standalone(steering=None) 경로에서 kis_reconcile job 등록 검증

## Phase 6 — 검증
- [x] 6.1 import/lint clean (worktree)
- [x] 6.2 unit+PBT 실행 — **누적 611 passed**(KIS 모킹 — 네트워크 비의존)
- [ ] 6.3 (선택) docker-verify 또는 main venv read-only smoke — 실제 KIS 모의 호출은 자격증명 준비 후 사용자 단계

## 생성 정책
- monorepo-refactor-as-native: `trading.symbols` 이관은 "원래 그랬던 것처럼" 깔끔히(마이그레이션 강조 주석 금지; 사연은 커밋 메시지).
- 멀티마켓 동시(Alpaca+KIS)는 F30 범위 밖(F33). F30은 KIS 단독 경로 + universe 추상화까지.
