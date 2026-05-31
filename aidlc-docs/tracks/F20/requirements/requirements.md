# F20 — 임의 종목 읽기 도구(Alpaca MCP stock-only read tools) 요구사항

> 부모 문서: [[f9-gated-alpaca-orders]] §5 (F9에서 읽기는 의도적으로 보류)  
> 트랙 상태: `aidlc-docs/tracks/F20/state.md`  
> 확정 질문·답변: `aidlc-docs/tracks/F20/requirements/questions.md`  
> 네이밍 규칙: [Alpaca MCP Server 공식 문서](https://docs.alpaca.markets/us/docs/alpaca-mcp-server) 기준 **stock-only 실용 서브셋, 이름·파라미터 1:1 매칭** (Q1=C→C-2)

## Intent Analysis

| 항목 | 분석 |
|------|------|
| **사용자 요청** | 운영자 콘솔에 Alpaca MCP 공식 읽기 도구 중 stock-only 서브셋을 정확한 이름으로 추가. 임의 종목 시세·주문·포지션 데이터를 AI가 직접 조회. |
| **요청 유형** | New Feature |
| **범위** | Multiple Components — 콘솔 TS(MCP 도구 + Alpaca HTTP 클라이언트) + env 배선(opencode config + docker-compose.verify.yml) + 서브모듈(포크 opencode permission keys) |
| **복잡도** | Moderate — TS 신규 모듈 + API 자격증명 신규 배선 + 서브모듈 권한 키. 아키텍처는 단순(인프로세스 HTTP 호출, 데몬 왕복 없음). |

## 핵심 아키텍처 결정 (Q2=A)

**콘솔 인프로세스(TS에서 Alpaca 데이터 API 직접 호출)**  
MCP 서버(bun/TS)가 Alpaca REST API를 직접 호출하여 시세·주문·포지션을 조회한다.
데몬 왕복 없음, 신규 FileDrop 채널 불필요, 데몬 코드 변경 없음.
대신 **Alpaca API 자격증명(Key + Secret)을 MCP 서버 환경변수에 새로 배선**해야 한다.

## Functional Requirements

### FR-1: Alpaca MCP 읽기 도구 — Stock-Only 서브셋 (TS 인프로세스)

MCP 서버에 Alpaca MCP 공식 읽기 도구 중 **stock-only 16개**를 추가한다.
모든 도구는 **읽기 전용(read-only, no order authority)** 이며,
`operator-console/src/mcp-server.ts`의 `server.registerTool()`로 등록한다.
도구 이름은 Alpaca MCP 공식 문서와 **정확히 1:1 매칭** (C-2).

#### FR-1.1 계좌·포지션·포트폴리오 (Trading Read)

| # | Tool | Alpaca MCP 원본 | 파라미터 |
|---|------|----------------|----------|
| 1 | `get_account_info` | ✅ | (없음) — 계좌 요약(equity, cash, buying_power, daytrade_count, PDT, status 등) |
| 2 | `get_all_positions` | ✅ | (없음) — 모든 오픈 포지션 목록 |
| 3 | `get_open_position` | ✅ | `symbol_or_asset_id: string` — 단일 종목 포지션 상세 |
| 4 | `get_portfolio_history` | ✅ | `period?: string` (1D/1W/1M/3M/6M/1A/5A/all), `timeframe?: string` (1Min/5Min/15Min/1H/1D), `intraday_reporting?: string` — PnL·equity 시계열 |

#### FR-1.2 자산·장 정보

| # | Tool | Alpaca MCP 원본 | 파라미터 |
|---|------|----------------|----------|
| 5 | `get_asset` | ✅ | `symbol_or_asset_id: string` — 단일 자산 정보(tradable 여부, exchange, marginable 등) |
| 6 | `get_all_assets` | ✅ | `status?: string` (active/inactive), `asset_class?: string` (us_equity), `exchange?: string` — 거래 가능 종목 필터링 |
| 7 | `get_calendar` | ✅ | `start?: string` (YYYY-MM-DD), `end?: string` — 거래일·공휴일 정보 |
| 8 | `get_market_clock` | ✅ | (없음) — 장 열림/닫힘/is_open/next_open/next_close |

#### FR-1.3 주식 시세·체결·봉 (Stock Market Data)

| # | Tool | Alpaca MCP 원본 | 파라미터 |
|---|------|----------------|----------|
| 9 | `get_stock_bars` | ✅ | `symbol_or_symbols: string` (comma-separated), `timeframe: string` (1Min/5Min/15Min/30Min/1Hour/1Day), `start?: string` (ISO), `end?: string` (ISO), `limit?: int`, `adjustment?: string` (raw/split/dividend/all) |
| 10 | `get_stock_latest_bar` | ✅ | `symbol_or_symbols: string` — 가장 최근 1개 봉 |
| 11 | `get_stock_latest_quote` | ✅ | `symbol_or_symbols: string` — 가장 최근 호가(bid/ask/크기/시각) |
| 12 | `get_stock_latest_trade` | ✅ | `symbol_or_symbols: string` — 가장 최근 체결(가격·수량·시각·거래소). "현재가?" 1차 도구 |
| 13 | `get_stock_quote` | ✅ | `symbol_or_symbols: string`, `start?: string`, `end?: string`, `limit?: int` — 과거 호가 시계열 |
| 14 | `get_stock_snapshot` | ✅ | `symbol_or_symbols: string` — 종합 스냅샷(latest trade + quote + minute bar + daily bar + previous daily bar). 단일 호출로 시세·OHLCV·전일 종가 모두 제공 |
| 15 | `get_stock_trades` | ✅ | `symbol_or_symbols: string`, `start?: string`, `end?: string`, `limit?: int` — 과거 체결 시계열 |

#### FR-1.4 주문 조회 (Trading Read)

| # | Tool | Alpaca MCP 원본 | 파라미터 |
|---|------|----------------|----------|
| 16 | `get_orders` | ✅ | `status?: string` (open/closed/all), `limit?: int`, `after?: string` (ISO), `until?: string` (ISO), `direction?: string` (asc/desc), `symbol?: string` — 주문 목록 필터링 조회 |

#### 명시적 제외 (Stock-Only 규칙)

Alpaca MCP의 다음 도구들은 **제외**:
- **Crypto** (8개): `get_crypto_bars`, `get_crypto_quotes`, `get_crypto_trades`, `get_crypto_latest_quote`, `get_crypto_latest_bar`, `get_crypto_latest_trade`, `get_crypto_snapshot`, `get_crypto_latest_orderbook`
- **Options** (2개): `get_option_contracts`, `get_option_latest_quote`, `get_option_snapshot`
- **Watchlist** (2개): `get_watchlists`, `get_watchlist_by_id`
- **Corporate Actions** (1개): `get_corporate_actions`

### FR-2: Alpaca HTTP 클라이언트 (신규 TS 모듈)

`operator-console/src/alpaca-data.ts` (신규):
- bun 내장 `fetch`로 Alpaca REST API v2 호출.
- `ALPACA_API_KEY` + `ALPACA_API_SECRET` 환경변수에서 자격증명 로드. **키가 없으면 MCP 서버 시작 거부** (`process.exit(1)` + stderr 진단 메시지). Fail-fast로 환경 구성 오류를 조기에 발견 (Application Design Q1=B).
- Base URL: `https://data.alpaca.markets`(data tools: #9~15) / `https://paper-api.alpaca.markets`(trading tools: #1~8, #16).
- 반환: JSON 응답 → **마크다운 테이블/불릿 리스트** 포맷으로 변환 (AI 파싱 최적화, Application Design Q2=A).
- 파라미터 검증: Zod schema로 타입·범위 검증. `symbol_or_symbols`는 `z.string()`(comma-separated, Alpaca MCP 1:1 매칭, Application Design Q3=A) (SECURITY-05).

### FR-3: 환경변수 배선

4곳에 Alpaca API 자격증명을 추가:
1. **`opencode.json` / `.opencode/opencode.jsonc`** (MCP env): `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER` 추가 — `AUTOSTOCK_ROOT`·`STEERING_OPERATOR_TOKEN`과 동일한 `{env:...}` 패턴. `ALPACA_PAPER` 기본값 `"true"` → `paper-api.alpaca.markets`. `"false"` → `api.alpaca.markets`. 데몬 `BrokerConfig.paper: bool`과 대응.
2. **`docker-compose.verify.yml`** (`attach` 서비스): 동일 변수 추가, host `.env`에서 전달 (F18이 배선한 `AUTOSTOCK_ROOT`·`STEERING_OPERATOR_TOKEN` 패턴과 동일).
3. **런타임 문서**: `scripts/worktree-setup.sh`에 Alpaca 키 필요성 기재.

### FR-4: opencode Permission Keys

- 모든 새 도구는 `opencode.json` permission 블록에 `"allow"`로 등록 (Q4=A — 비변경이므로 사람 확인 불필요).
- 키 네임스페이스: `autostock_<tool_name>` — 예: `autostock_get_stock_latest_trade`, `autostock_get_orders`, `autostock_get_account_info` 등 16개.
- 서브모듈(operator-console/cli)에도 동일 키 추가 (Q6=A — 같은 트랙에서 처리, F19와 동일 패턴).

### FR-5: 시장 마감 시 의미 구분 (Q3=D)

각 도구 응답에 충분한 컨텍스트를 포함하여 AI가:
- **"종가"**: 전일 종가(`prev_daily_bar.close`) 또는 당일 종가(장 마감 후 daily bar close)를 보고 판단.
- **"현재가"**: 시간외 체결을 포함한 latest trade price를 보고 판단.
- 공통: 각 가격 옆에 타임스탬프 + `market_open` 여부를 표기.

### FR-6: IEX 무료 피드 (Q5=A)

- 데이터 API 호출 시 특별한 피드 지정 없음 → Alpaca 기본값(IEX, 무료 플랜).
- 레이트 제한은 운영 규모상 특별 대응 불필요. 단, HTTP 429 응답 시 적절한 오류 메시지 반환.

### FR-7: AI 소비용 텍스트 출력 포맷 (Q2=A)

- Alpaca JSON 응답을 **마크다운 테이블/불릿 리스트**로 변환하여 MCP `text` content로 반환.
- AI가 수치를 쉽게 파싱할 수 있는 구조. 예: `| AAPL | $195.83 | 2024-06-15T16:00:00Z | NASDAQ |`
- 중복 필드는 필요한 것만 추출 (전체 JSON 그대로 반환하지 않음) — 토큰 효율.

### FR-8: 심볼 파라미터는 comma-separated string (Q3=A, Alpaca MCP 1:1)

- `symbol_or_symbols: z.string()` — Alpaca MCP 공식 시그니처와 정확히 매칭.
- 내부에서 `split(",").map(s => s.trim())` 처리.
- F21(`place_stock_order` arg robustness)과 머지 시 Zod schema 통일성 확인 필요.

### FR-9: `steer_read`와 F20 도구 간 데이터 신뢰도 계층 (critic M1)

- `steer_read`(daemon snapshot)는 주기적 갱신으로 **stale 가능** — positions/orders/account 조회에는 **F20 live Alpaca API 도구를 우선 사용**.
- `steer_read`는 데몬 내부 상태(**run_state, agent-trace, why, turns, decisions, log, locked_symbols**)에만 사용.
- 각 F20 도구 description에 "live Alpaca API — fresher than daemon snapshot" 표기.
- `steer_read` 도구 description에 "returns daemon snapshot; for live Alpaca data use get_* tools" 추가.
- 두 경로 응답 충돌 시 F20(live Alpaca)이 더 최신 → 신뢰.

## Non-Functional Requirements

### NFR-1: Advisor-Only 불변성 (기존 F4 규칙 계승)
- 모든 새 도구는 읽기 전용. 주문·취소·변경 권한 없음.
- opencode `allow`로 게이트 → human confirm 없이 AI 임의 호출 가능 (비변경이므로 안전).

### NFR-2: TS 단일 진실원 아님 (중복 허용)
- Alpaca HTTP 호출은 TS에서 직접 수행하므로 파이썬 `AlpacaBroker.get_latest_prices`와 일부 중복.
- 이는 **의도적**: 읽기는 콘솔이 자체 해결, 쓰기는 데몬이 관장 → 책임 분리(FR-1=TS, 주문=Python).

### NFR-3: Cross-Language Contract 불필요
- FileDrop 요청/응답 채널을 만들지 않으므로 기존 `commands.jsonl` / `events.jsonl` / `snapshot.json` 형식 영향 없음.
- `steer_read`(snapshot/monitor)는 그대로 유지 — 신규 도구와 보완 관계.

### NFR-4: 오류 처리 (Fail-Closed + Graceful)
- Alpaca API 연결 실패 → "Alpaca API unavailable" 메시지 + 원인 (HTTP status + body prefix).
- HTTP 429(Rate Limit) → "Rate limited, retry after X seconds".
- 잘못된 심볼 → API 에러 메시지를 그대로 AI에 전달.
- `ALPACA_API_KEY` 미설정 → `process.exit(1)` + stderr `[autostock] ALPACA_API_KEY and ALPACA_API_SECRET must be set`. MCP 서버 시작 거부 (Q1=B: fail-fast).
- 스택 트레이스·내부 경로 노출 금지 (SECURITY-09).

### NFR-5: 자격증명 보안
- `ALPACA_API_KEY` + `ALPACA_API_SECRET`은 env에서만 로드, 로그·MCP 응답에 절대 포함 금지 (SECURITY-12).
- `paper-api.alpaca.markets` 엔드포인트 사용 (paper trading only — F20 상태 개요와 일치).

### NFR-6: PBT Framework (PBT-09)
- TypeScript: `fast-check` — Jest/Vitest 통합, custom generators, shrinking, seed reproducibility.
- Python: `hypothesis` — 신규 Python 코드 없으면 TS만 fast-check.

---

## Extension Configuration

| Extension | Enabled | Decided At |
|-----------|---------|------------|
| Security Baseline | Yes | Requirements Analysis (2026-05-31) |
| Property-Based Testing | Yes | Requirements Analysis (2026-05-31) |

### Security Baseline Compliance (Requirements Stage)

| Rule | Applicable? | Assessment |
|------|------------|------------|
| SECURITY-01 (Encryption at Rest/Transit) | N/A | 데이터 저장소 없음. TS→Alpaca는 HTTPS(TLS 1.2+). |
| SECURITY-02 (Network Access Logging) | N/A | 중간 네트워크 장비 없음(인프로세스 HTTPS 콜). |
| SECURITY-03 (App-Level Logging) | N/A | 콘솔 MCP 서버는 로깅 인프라 없음. 오류는 MCP text 응답으로 반환. |
| SECURITY-04 (HTTP Security Headers) | N/A | HTML 서빙 엔드포인트 없음(MCP stdio). |
| **SECURITY-05** (Input Validation) | **Compliant** | → Zod schema로 모든 파라미터 타입·범위·심볼 포맷 검증 (FR-1, FR-2). |
| SECURITY-06 (Least-Privilege) | N/A | IAM/클라우드 정책 없음(로컬 프로세스). API 키는 paper trading only. |
| SECURITY-07 (Network Configuration) | N/A | 방화벽 규칙 없음(아웃바운드 HTTPS only). |
| SECURITY-08 (Application Access Control) | N/A | 사용자 인증 없음(로컬 콘솔, 토큰 기반). 읽기 도구는 `allow`로 게이트. |
| **SECURITY-09** (Security Hardening) | **Compliant** | → 기본 자격증명 없음(env에서만). 오류 메시지에 스택 트레이스·내부 경로 미포함(NFR-4). |
| SECURITY-10 (Supply Chain) | N/A | 신규 의존성 없음(bun 내장 fetch 사용). 기존 `bun.lock`이 lockfile 역할. |
| **SECURITY-11** (Secure Design) | **Compliant** | → 읽기/쓰기 책임 분리(TS=read, Python=write). Defense in depth: Alpaca API 키는 paper only, 쓰기는 RiskManager gate 추가. Rate limiting은 Alpaca API 자체에 위임. |
| **SECURITY-12** (Credential Management) | **Compliant** | → NFR-5: env-only, 로그·응답에 미포함, paper endpoint. |
| SECURITY-13 (Data Integrity) | N/A | 외부 CDN 스크립트 없음. 역직렬화는 Alpaca JSON 응답만(알려진 스키마). |
| SECURITY-14 (Alerting/Monitoring) | N/A | 운영자 콘솔이 직접 사용하는 도구. 알림 인프라 없음. |
| **SECURITY-15** (Exception Handling) | **Compliant** | → NFR-4: API 오류 graceful 처리, fail-closed, 리소스 정리(fetch 응답은 GC). |

**Security Summary**: 5 rules applicable, all compliant at requirements stage. 나머지 10개 규칙은 N/A.

### PBT Compliance (Requirements Stage)

| Rule | Applicable? | Assessment |
|------|------------|------------|
| PBT-01 (Property Identification) | Deferred → Functional Design | 설계 단계에서 각 도구의 testable property 식별. |
| PBT-09 (Framework Selection) | **Compliant** | → NFR-6: TS=`fast-check`, Python=`hypothesis`(if needed). |
| Others (PBT-02~08, PBT-10) | Deferred → Code Generation | 코드 생성 단계에서 적용. |

---

## Out of Scope (명시적 제외)

- **주문·취소·변경**: F9가 이미 제공. 읽기 전용.
- **데몬 코드 변경**: Q2=A로 데몬 영향 없음.
- **`steer_read` 교체/제거**: 기존 snapshot/monitor 경로는 그대로 유지. 신규 도구와 보완 관계.
- **스트리밍(WebSocket)**: 1차 구현은 REST only.
- **Crypto / Options / Watchlists / Corporate Actions**: Alpaca MCP에 존재하지만 stock-only 서브셋에서 제외 (C-2).
