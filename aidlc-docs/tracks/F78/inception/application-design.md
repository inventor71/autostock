# F78 — Application Design (경량)

**Date**: 2026-06-13 · **Base**: bacd341 · 깊이: 경량 (Functional + NFR Design 흡수)
**원칙**: F61 signals 구조를 그대로 따라가는 **additive** 설계. earnings 경로의 형제로 IPO 경로를 붙인다.

## 0. 핵심 설계 분기 (earnings와 다른 점) ⚠️
earnings 선별(`select_imminent_earnings`)은 **universe∪held로 필터**한다. 그러나 IPO는 정의상
universe에 없는 신규 종목 → **universe 필터를 적용하지 않는다.** "임박 US IPO 전부"를 규모순으로
surfacing하고, 우연히 universe/held에 이미 있으면 **태그만** 단다(필터 아님). 이것이 본 트랙의
설계 정체성: 인지 채널은 universe 밖을 봐야 한다.

## 1. 데이터 모델 (`src/signals/records.py`, additive)

```python
# Input row (fed to the pure selector) — mirrors EarningsRow
class IpoRow(BaseModel):
    symbol: str | None = None          # Finnhub may omit a ticker pre-pricing
    name: str                          # company name (always present)
    ipo_date: _date
    exchange: str | None = None
    status: Literal["expected","priced","withdrawn","filed","unknown"] = "unknown"
    shares: int | None = None
    price_low: float | None = None     # parsed from "13.00-15.00" or "135.00"
    price_high: float | None = None
    est_value: float | None = None     # totalSharesValue — size proxy

# Output (brief row) — mirrors ImminentEarnings
class ImminentIpo(BaseModel):
    name: str
    symbol: str | None = None
    ipo_date: _date
    exchange: str | None = None
    status: Literal[...] = "unknown"
    est_value: float | None = None     # sort key (size desc)
    in_universe: bool = False          # tag only (rare: IPO already added to universe)
    is_held: bool = False              # tag only
```
- 모두 pydantic → 직렬화 라운드트립(PBT-02 선례 + 본 트랙 PBT 대상).
- `withdrawn` 상태는 선별에서 제외(상장 안 함). `expected`/`priced`/`filed`만 surfacing.

## 2. 선별 pure core (`src/signals/ipo_cal.py` 신규 — `earnings_cal.py` 미러)

```python
def select_imminent_ipos(
    rows: list[IpoRow], *, today: date, horizon_days: int, max_ipos: int,
    universe: set[str], held: set[str],
) -> list[ImminentIpo]:
    # 1. 날짜 창 [today, today+horizon] 내 + status != withdrawn
    # 2. universe 필터 없음 — 전부 후보. universe/held면 in_universe/is_held 태그
    # 3. 정렬: est_value desc (None은 후순위), tie-break ipo_date asc, name
    # 4. max_ipos 캡
```
- **pure / 멱등** (PBT 대상): 정렬 안정성, 캡 경계, horizon 경계, withdrawn 제외, 태깅.

## 3. 소스 (`src/signals/sources/finnhub_ipo.py` 신규 — `finnhub_earnings.py` 미러)

```python
_BASE_URL = "https://finnhub.io/api/v1/calendar/ipo"   # earnings와 동일 인증/타임아웃 패턴

class FinnhubIpoCalendar:
    def __init__(self, api_key, *, http_connect_timeout=3.0, http_read_timeout=5.0): ...
    def get_calendar(self, from_date, to_date) -> list[IpoRow]:
        # GET ?from&to&token → raise_for_status() (호출자 degrade)
        # payload["ipoCalendar"] 각 항목 방어적 파싱:
        #   date/name 없으면 skip. price 문자열 "lo-hi" 또는 "x" → price_low/high.
        #   numberOfShares→shares, totalSharesValue→est_value, status 매핑(미지 → "unknown")
```
- **Finnhub 응답 스키마(구현 시 라이브 재확인)**: `{"ipoCalendar":[{date, exchange, name,
  numberOfShares, price, status, symbol, totalSharesValue}]}`. `price`는 문자열(범위 가능),
  `status` ∈ expected/priced/withdrawn/filed.
- transport/HTTP 오류는 **raise** — collector가 degrade 판정(earnings와 동일 규약).

## 4. 설정 (`src/signals/settings.py`, additive)

```python
class SignalSources(BaseModel):
    ...
    ipo_provider: Literal["finnhub","none"] = "finnhub"

class SignalsConfig(BaseModel):
    ...
    ipo_horizon_days: int = Field(default=5, ge=0)   # earnings(2)보다 약간 길게 — IPO 일정 여유
    max_ipos: int = Field(default=8, ge=1)           # brief 비대화 방지 캡
```
- `settings.yaml signals:` 블록에서 오버라이드(빈 블록 → 시드 디폴트로 동작, FR-7).

## 5. Brief 통합 (`records.py` + `brief.py`)
- `MarketSignalBrief.imminent_ipos: list[ImminentIpo] = []` 필드 추가.
- `assemble_brief(...)` 시그니처에 `imminent_ipos` 인자 추가(순수 번들링 유지).
- `MarketSignalBrief.is_empty()`에 `imminent_ipos` 포함.
- `to_prompt_text()` — earnings 블록 **다음**에 섹션:

```text
Imminent IPOs / catalysts (next 5d — awareness, NOT a buy menu):
  - SPCX (Space Exploration Technologies) 2026-06-12 NASDAQ ~$75.1B [priced]
  - ACME (Acme Robotics) 2026-06-16 NYSE ~$1.2B [expected]
```
- 표기: 심볼(있으면)·회사명·상장일·거래소·규모(est_value 가용 시 `~$Xb`)·`[status]`.
  universe/held 태그는 `[HELD]`/`[universe]` 접미. 라벨에 "awareness, NOT a buy menu" 명시로
  day-1 IPO 직매수 오인 방지(비범위 강화).

## 6. Collector 통합 (`src/signals/collector.py`)
- `__init__`에 `ipo_source=None` 주입 인자 추가(테스트 fake 주입 가능, earnings_source 대칭).
- `collect()` 시그니처에 `ipo_horizon_days: int | None = None` 추가 → **cache_key에 포함**
  (earnings horizon과 독립적으로 오버라이드 가능; push 경로는 둘 다 None → config 디폴트).
- `_imminent_ipos(today, held, universe_set, degraded, ipo_horizon)` 신규 (earnings 미러):
  - source None → `degraded.append("ipo:disabled")`, `[]`.
  - `get_calendar` 예외 → `logger.warning` + `degraded.append("ipo:finnhub")`, `[]`.
  - 성공 → `select_imminent_ipos(...)`.
- `assemble_brief(movers, alerts, imminent, imminent_ipos, degraded)` 호출 업데이트.
- `from_settings`: `_build_ipo_source(config, settings)` 추가(`_build_earnings_source` 미러 —
  `ipo_provider=="finnhub"` + `FINNHUB_API_KEY` 있을 때만, 없으면 None + info 로그).

## 7. Pull 도구 parity (`market.py` + `__main__.py` + `prompts.py` + `fixtures.py`)
- `market.ipo_calendar(collector, days=None)` — `earnings_calendar` 미러:
  `collector.collect(ipo_horizon_days=days)` → `{as_of, imminent_ipos[], degraded_sources}`.
- `__main__.py`: `ic = sub.add_parser("ipo_calendar"); ic.add_argument("--days", type=int, ...)`
  + dispatch `out = market.ipo_calendar(_signal_collector(), days=args.days)`.
- **NFR-4 (하드)**: `fixtures.MARKET_COMMANDS`에 `"ipo_calendar"` 추가 → eval 턴 라이브 미접촉.
- `prompts._SIGNAL_TOOL_GUIDE`에 항목 추가:
  `"ipo_calendar": "...ipo_calendar — imminent US IPOs within the horizon (size-ranked, awareness)"`.

## 8. Regime nudge (`prompts.py` step 2, additive — Discovery 미변경)
현재:
```
2. Regime: refresh regime.md — SPY/QQQ/VIX, sector posture, macro — using the
   tools and web research.
```
변경(한 문장 추가):
```
2. Regime: refresh regime.md — SPY/QQQ/VIX, sector posture, macro — using the
   tools and web research. Also scan top-down for market-moving catalysts not yet
   tied to a ticker — imminent IPOs (see the brief's IPO list), M&A, regulatory,
   macro prints — and note their sector/sentiment impact and any read-through to
   held or universe names in regime.md. (You may NOT trade a name outside the
   tradeable universe; this is awareness, not a buy list.)
```
- multi-agent research 프롬프트(`multi_research_initial_prompt`)에도 동일 가이드가 흐르도록
  signal guide에 ipo_calendar가 포함됨(§7).

## 9. NFR Design 요약 (흡수)
| NFR | 설계 |
|---|---|
| NFR-1 fail-honest | source 실패 → `degraded_sources`("ipo:finnhub"/"ipo:disabled"), 턴 정상 |
| NFR-2 timeout (하드) | `FinnhubIpoCalendar`가 earnings와 동일 `(connect, read)` 타임아웃. 추가 스레드 불필요(단일 HTTP, yfinance 같은 무바운드 백엔드 아님) |
| NFR-3 cache | push/pull 단일 collect 공유. ipo_horizon override는 cache_key에 포함 |
| NFR-4 eval seam (하드) | `ipo_calendar` ∈ MARKET_COMMANDS → fixture 가로채기 적용 |
| NFR-5 security | `FINNHUB_API_KEY` env-only(기존 `settings.finnhub_api_key`), 키 로그/예외 비노출, 응답 방어 파싱(누락/형식 이상 행 skip) |

## 10. 변경 파일 인벤토리
- **신규**: `src/signals/sources/finnhub_ipo.py`, `src/signals/ipo_cal.py`,
  `tests/signals/test_ipo_cal.py` (+ 소스/통합 테스트)
- **수정(additive)**: `records.py`, `brief.py`, `settings.py`, `collector.py`,
  `agent/tools/market.py`, `agent/tools/__main__.py`, `agent/tools/fixtures.py`,
  `agent/prompts.py`, `config/settings.yaml`(signals 블록 디폴트 주석)
- **회귀 리스크**: `assemble_brief`/`collect` 시그니처 확장 → 호출부 동기화 필요(주로 collector
  내부 + market.py). 기존 F61 테스트 회귀 없음 확인이 Build&Test 게이트.
