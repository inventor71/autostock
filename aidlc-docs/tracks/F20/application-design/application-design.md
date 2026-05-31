# F20 Application Design — Consolidated

> 집약 문서. 상세는 개별 파일 참조:
> - `components.md` — 컴포넌트 정의·책임·인터페이스
> - `component-methods.md` — 전체 메서드 시그니처 (16개 도구별 Alpaca API 매핑)
> - `services.md` — 서비스 계층·오케스트레이션·라이프사이클
> - `component-dependency.md` — 의존성 매트릭스·통신 패턴·데이터 흐름
> - `application-design-plan.md` — 설계 질문·답변 (Q1=B fail-fast, Q2=A markdown table, Q3=A comma-sep string)

---

## 설계 개요

**F20은 콘솔 TS 인프로세스에서 Alpaca REST API v2를 직접 호출하여 16개 Alpaca MCP stock-only 읽기 도구를 제공한다.** 데몬 왕복 없음, FileDrop 신규 채널 없음, 데몬 코드 변경 없음.

## 핵심 설계 결정 (Q&A)

| 질문 | 결정 | 근거 |
|------|------|------|
| Q1: 키 누락 시 | **Fail-fast** — `process.exit(1)` | 의도적 설계 결정 (critic reviewed). F18은 graceful degradation(토큰 없어도 서버 시작, 쓰기만 거부)이나, F20은 다르게 판단 — Alpaca 키 없이 띄운 MCP 서버는 읽기 16개가 dead weight. 환경 구성 오류를 조기에 발견하고 operator가 즉시 수정하도록 강제. 기존 9개 도구(steer/steer_read/F9)도 함께 사용 불가 — 이 tradeoff는 의도적이며, operator가 Alpaca 키를 제대로 설정할 때까지 전체 MCP 서버를 사용할 수 없음. |
| Q2: 텍스트 포맷 | **마크다운 테이블/불릿** | AI 파싱 최적화. 토큰 효율(전체 JSON 대비). |
| Q3: 심볼 파라미터 | **`z.string()` comma-separated** | Alpaca MCP 1:1 매칭. F21 머지 시 Zod 통일성 확인 필요. |

## 컴포넌트 아키텍처

```
mcp-server.ts (MODIFY)
├── import AlpacaDataClient
├── const client = new AlpacaDataClient()   ← fail-fast: 키 없으면 exit(1)
└── server.registerTool(...) x16            ← 기존 steer/steer_read/F9 도구 아래 추가

alpaca-data.ts (NEW)
├── class AlpacaDataClient
│   ├── constructor()          ← env 검증 + authHeaders
│   ├── getAccountInfo()       ← GET /v2/account
│   ├── getAllPositions()      ← GET /v2/positions
│   ├── getOpenPosition(s)     ← GET /v2/positions/{symbol}
│   ├── getPortfolioHistory()  ← GET /v2/account/portfolio/history
│   ├── getAsset(s)            ← GET /v2/assets/{id}
│   ├── getAllAssets()         ← GET /v2/assets
│   ├── getCalendar()          ← GET /v2/calendar
│   ├── getMarketClock()       ← GET /v2/clock
│   ├── getOrders()            ← GET /v2/orders
│   ├── getStockBars()         ← GET /v2/stocks/{syms}/bars
│   ├── getStockLatestBar()    ← GET /v2/stocks/{syms}/bars/latest
│   ├── getStockLatestQuote()  ← GET /v2/stocks/{syms}/quotes/latest
│   ├── getStockLatestTrade()  ← GET /v2/stocks/{syms}/trades/latest
│   ├── getStockQuote()        ← GET /v2/stocks/{syms}/quotes
│   ├── getStockSnapshot()     ← GET /v2/stocks/{syms}/snapshots
│   └── getStockTrades()       ← GET /v2/stocks/{syms}/trades
│
├── helpers
│   ├── tradingGet() / dataGet()  ← bun fetch wrapper + error handling
│   ├── formatTable()             ← array → markdown table
│   ├── formatBullets()           ← object → key-value bullets
│   └── formatSnapshot()          ← snapshot → sectioned markdown
│
└── Zod schemas (per-tool input validation)
    ├── PortfolioHistoryParams
    ├── AssetFilterParams
    ├── CalendarParams
    ├── OrderFilterParams
    ├── StockBarsParams
    ├── StockQuoteParams
    └── StockTradesParams
```

## 의존성

| 방향 | 관계 |
|------|------|
| `mcp-server.ts` → `alpaca-data.ts` | import (컴파일타임 의존성) |
| `alpaca-data.ts` → `process.env` | runtime — `ALPACA_API_KEY`, `ALPACA_API_SECRET` |
| `alpaca-data.ts` → Alpaca API | runtime — HTTPS outbound |
| 데몬 | **의존성 없음** — 읽기 전용, 데몬 코드 변경 없음 |
| `steer_read` / snapshot | **영향 없음** — 기존 읽기 경로 유지, 신규 도구와 보완 |
| 서브모듈 opencode config | **병렬 변경** — permission keys + env vars. gitlink merge 시점까지 분리. |

## 영향받는 파일 (변경 범위)

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `operator-console/src/alpaca-data.ts` | **NEW** | Alpaca HTTP 클라이언트 + 포맷터 |
| `operator-console/src/mcp-server.ts` | **MODIFY** | 16개 registerTool 추가 |
| `operator-console/cli/opencode.json` | **MODIFY** (submodule) | 16 permission keys + 2 env vars |
| `operator-console/cli/.opencode/opencode.jsonc` | **MODIFY** (submodule) | 동일 |
| `docker-compose.verify.yml` | **MODIFY** | attach 서비스에 ALPACA_KEY + SECRET 전달 |
| `scripts/worktree-setup.sh` | **MODIFY** | Alpaca 키 문서화 |

## PBT-01: Testable Properties (Functional Design 으로 이관)

| 컴포넌트 | Property Category | 예비 식별 |
|----------|------------------|-----------|
| `formatTable` | Invariant — 출력 행 수 = 입력 배열 길이 (최대 limit까지) | Round-trip 아님 (JSON→MD는 lossy) |
| `tradingGet` / `dataGet` | Invariant — HTTP 2xx만 성공, 그 외는 오류 문자열 | |
| Zod schemas | Round-trip? — `z.parse(z.output(schema))` = identity | Functional Design에서 확정 |
| `getStockBars` → format | Idempotence — 동일 파라미터 → 동일 마크다운 구조 (값은 다를 수 있음) | |

Extension rule PBT-01 requires formal identification in Functional Design stage.
