# F95 — Application Design

> Track F95 · Application Design. 두 유닛의 컴포넌트·메서드·비즈니스 규칙·의존성과 **경계(계약)**를 정의.
> 실제 코드 기준(파일:라인 인용). 세부 스키마·상태전이는 Functional Design에서 확정.

## 0. 컴포넌트 경계 개요

```
[Python 데몬 (U1)]                                  [TS TUI (U2)]
 SteeringRuntime                                     SymbolOverlay
  ├ _quote_candidates()  ── held∪orders∪recent       ├ useQuote(steeringDir, symbol)  ← reads
  │                          decision/interv          │     steering/quotes.json (poll ~1.5s)
  ├ refresh_quotes()  ── data_provider batch          ├ Quote 섹션(항상 표시, as-of/loading/err)
  │   fetch → QuoteBook → write ─────────────►  steering/quotes.json  (계약)
  └ add_seconds_job(refresh_quotes, ~2s)              intervention-overlay: symbol span onMouseUp
                                                        → onSymbolClick → overlay.openSymbol (기존)
```

**Seam(계약)** = `steering/quotes.json` (인스턴스별 steering 경로, 단일 writer=refresh_quotes).
스키마 확정 후 U1/U2 병렬 구현 가능.

---

## 1. Unit U1 — 데몬 Quote Warm-Cache Producer (Python, `src/`)

### 1.1 컴포넌트 & 책임
- **`QuoteBook`** (신규, 경량) — in-memory `dict[str, tuple[float, datetime]]` + TTL. 기존 `_price_book`(runtime.py:178,433-443, TTL 30s) 패턴 재사용/일반화. 책임: 최신 시세 캐시 보관·신선도 판단.
- **`SteeringRuntime._quote_candidates() -> set[str]`** (신규) — 클릭-후보 심볼 집합 산출. `held ∪ open_orders ∪ 최근 N개 decision/intervention 심볼`, 상한(cap, 예 ~30)으로 바운드. 소스: `broker.get_portfolio_state().positions`, `broker.get_open_orders()`, monitor decisions(이미 데몬 in-proc), 인터벤션 레코드.
- **`SteeringRuntime.refresh_quotes()`** (신규, worker job) — `bus.submit(_build)`로 단일 워커에서: candidates 계산 → **`fetch_latest_prices(self.executor.data_provider, candidates)`** (src/data/prices.py, 동시성 배치) → QuoteBook 갱신 → `steering/quotes.json` **원자적 기록**. best-effort(실패 로깅, 무크래시) — `refresh_order_prices`(runtime.py:445-463)와 동형.
- **스케줄 등록** — `src/trading/modes/agent.py`(현재 snapshot@5s:735, order_prices@12s:757 근처)에 `self.scheduler.add_seconds_job(self.steering.refresh_quotes, <QUOTE_SECS≈2>, "steering_quotes")` 추가.

### 1.2 메서드 시그니처 (초안, Functional Design 확정)
```python
class QuoteBook:
    def get(self, symbol: str) -> tuple[float, datetime] | None: ...   # None=미보유/stale
    def put(self, symbol: str, price: float, ts: datetime) -> None: ...
    def as_payload(self) -> dict[str, dict]: ...                        # {sym: {price, ts}}

class SteeringRuntime:
    def _quote_candidates(self) -> set[str]: ...
    def refresh_quotes(self) -> None: ...   # bus.submit; fetch→QuoteBook→write quotes.json
```

### 1.3 비즈니스 규칙 (BR)
- **BR-U1.1 (시세 소스 = 데이터 provider)**: 시세는 `self.executor.data_provider`(계정-무관 전역 플레인, `create_data_provider` main.py:15-34)에서. **브로커 마킹가(broker.get_latest_prices) 아님** — 임의 종목·실시장 시세 목적. (held 포지션의 snapshot `current_price`는 별개로 브로커 마킹가 유지.)
- **BR-U1.2 (단일 writer + 원자적)**: `quotes.json`은 refresh_quotes만 기록(원자적 tmp→rename, src/agent/steering/jsonl.py 헬퍼). torn-read 방지. snapshot.json은 건드리지 않음(분리 파일 → 2s 시세 신선도가 5s snapshot에 종속되지 않음).
- **BR-U1.3 (fail-honest)**: provider 조회 실패/키 부재/심볼 오류 → 해당 심볼 캐시 미갱신(또는 error 마킹), **데몬 무크래시**. yfinance 간헐 실패는 백오프/스킵. [[account-farm-sdk-schema-drift]].
- **BR-U1.4 (인스턴스 격리)**: quotes.json은 인스턴스 steering 볼륨에만. 지속 연결 없음 → websocket 한도/공유볼륨 무관(ADR §9). broker_api 인스턴스 동일.
- **BR-U1.5 (바운드)**: candidate 상한 + ~2s 배치로 provider 레이트리밋 보호. 상한 초과 시 우선순위(held>orders>recent).

### 1.4 의존성
`executor.data_provider`, `data.prices.fetch_latest_prices`, `bus`(단일 워커), `scheduler.add_seconds_job`, atomic write 헬퍼, monitor decisions/intervention 레코드 소스.

---

## 2. Unit U2 — TUI Quote Reader + Panel + Intervention 클릭 (TS, `operator-console/cli`)

### 2.1 컴포넌트 & 책임
- **`hooks/use-quote.ts`** (신규) — `readQuote(steeringDir, symbol): QuoteEntry | null` (readPositions 패턴, use-snapshot-data.ts:5-13과 동형, `quotes.json` 읽기·JSON.parse·try/catch). + 폴링 훅 `useQuote(steeringDir, symbol, intervalMs≈1500)`(use-monitor-data.ts:24-50 패턴, 값 변할 때만 setSignal).
- **`components/symbol-overlay.tsx`** (수정) — 헤더 아래 **Quote 섹션(항상 표시)** 추가: 헤드라인 최신가 + `as of HH:MM:SS`(fmtLocalHhmm 재사용) + 상태(로딩="조회 중"/에러="시세 없음"). position 섹션(50-60행)은 기존대로 held일 때만. **시세=항상, 현행=graceful**.
- **`components/intervention-overlay.tsx`** (수정) — symbol span(32행)을 클릭 가능하게: `onMouseUp={(e)=>props.onSymbolClick?.(iv().symbol, e.x, e.y)}` (turn-overlay.tsx:91-97 동형). `InterventionOverlayProps`에 `onSymbolClick?` 추가.
- **`routes/session/index.tsx`** (수정) — `<InterventionOverlay>` 렌더처(F95 대상)에 `onSymbolClick={(s,x,y)=>overlay.openSymbol(s,x,y)}` 전달(TurnOverlay 배선 index.tsx:1348과 동일). `overlay.openSymbol`은 기존(use-overlay.ts:23).

### 2.2 인터페이스 (초안)
```ts
export interface QuoteEntry { price: number; ts: string }        // from quotes.json
export function readQuote(steeringDir: string, symbol: string): QuoteEntry | null
export function useQuote(steeringDir: string, symbol: string, intervalMs?: number): () => QuoteEntry | null
// InterventionOverlayProps += onSymbolClick?: (symbol: string, x: number, y: number) => void
```

### 2.3 비즈니스 규칙 (BR)
- **BR-U2.1 (시세 always)**: Quote 섹션은 어떤 심볼이든 렌더. 값 있으면 가격+as-of, 없으면 로딩/"시세 없음"(조용한 생략 금지, FR-2).
- **BR-U2.2 (현행 graceful)**: position/thesis/decisions는 기존대로 존재 시만(Show), 없으면 생략(FR-3).
- **BR-U2.3 (as-of 정직)**: 표시 시각은 quotes.json ts. provider 지연(yfinance) 가능성은 as-of로 드러냄 — 실시간 허위 주장 금지.
- **BR-U2.4 (비회귀·상호작용 계승)**: openSymbol 토글/바깥클릭 닫힘/z-order 기존 유지([[opentui-zorder-hittest]]). turn·health 오버레이 무영향.

### 2.4 의존성
`quotes.json`(U1 계약), OverlayPanel, use-overlay.openSymbol(기존), format 유틸(fmtLocalHhmm/fmtPnl), intervention onSymbolClick 배선.

---

## 3. 경계 계약 & 통합
- **계약 파일**: `steering/quotes.json` — `{ "<SYM>": {"price": <float>, "ts": "<ISO8601>"}, "_meta": {"updated": "<ISO>", "provider": "<name>"} }` (정확한 형태는 Functional Design). 인스턴스별, 단일 writer.
- **fast-path**: 클릭 심볼이 snapshot positions에 있으면 position.current_price도 즉시 사용 가능. **주의(FD 확정)**: 헤드라인 시세=data_provider(실시장), position.current_price=broker 마킹가 → 값 상이 가능. 헤드라인은 시세, position 줄은 보유맥락으로 분리 표기.
- **캐시 미스**: candidate 밖 심볼 클릭(드묾) → "조회 중" 후 다음 refresh 편입 대기, 또는 온디맨드 트리거(FD에서 필요성 판단; 클릭 대상이 대개 candidate라 초기엔 미포함 가능).
- **구현 순서**: U1이 quotes.json 스키마 확정·생산 → U2 소비. 스키마 후 병렬. 통합=라운드트립(데몬 quotes.json 기록 ↔ TUI 표시) + fail-honest 테스트.

## 4. 미해결(Functional Design 입력)
- quotes.json 정확 스키마(등락/전일종가 포함 여부), candidate 상한 N·recent 윈도우, QUOTE_SECS 기본값(2s vs provider별 조정), 캐시-미스 온디맨드 채널 채택 여부, 헤드라인 시세 vs 마킹가 표기 규칙.
