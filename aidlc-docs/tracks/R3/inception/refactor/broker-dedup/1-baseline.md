# Stage 1 — Baseline: Alpaca-shaped broker dedup

**Track**: R3 · **Base commit**: ec2875c · **Date**: 2026-06-06

> Records *what the code does today* (not what is correct) so the refactor keeps a
> before/after-green safety net. Doubles as the onboarding doc for this area.

## 1. Scope & entry points

| File | LOC | Role |
|------|-----|------|
| `src/execution/brokers/alpaca_broker.py` (`AlpacaBroker`) | 602 | Production paper/live broker via **Alpaca Trading API** (`alpaca.trading`, `TradingClient`). The default live broker. |
| `src/execution/brokers/broker_api_broker.py` (`BrokerApiBroker`) | 593 | Sandbox **account-farm** broker via **Alpaca Broker API** (`alpaca.broker`, `BrokerClient`), per-account `*_for_account` endpoints. Selected for the F16 sandbox account farm. |
| `src/execution/base.py` (`BaseBroker`) | 167 | ABC both extend. Defines the public broker contract + emulated defaults. **Out of scope to change.** |
| `src/execution/brokers/kis_broker.py` (`KISBroker`) | 567 | Korean broker — **deliberately NOT part of this base** (different SDK, OCO emulation, tick rules — see [[kis-api-facts]]). |
| `src/execution/brokers/simulated.py` (`SimulatedBroker`) | 502 | In-memory backtest broker — unrelated. |

Both Alpaca-shaped brokers are constructed in the broker-selection wiring (factory in
`main.py` / mode setup) and consumed *only* through the `BaseBroker` interface by
`RiskManager`, `DecisionExecutor`, the agent loop, and the F8 sidebar. **No caller depends on
the concrete class** beyond construction — the whole point of `BaseBroker`.

## 2. Preserved observable contract (the `BaseBroker` surface)

Every method below must behave identically before/after. These are the externally observable
behaviors (return shapes, side effects, error semantics):

| Method | Contract to preserve |
|--------|----------------------|
| `submit_order(Order) -> FilledOrder` | Builds the SDK request, submits, polls to terminal/timeout, returns `FilledOrder` (filled_price may be 0 if still pending). Wraps all errors in `BrokerError`. |
| `get_order_status(id) -> FilledOrder \| None` | None on fetch failure; else latest fill state. |
| `cancel_order(id) -> bool` | True/False; never raises. |
| `close_position(symbol) -> FilledOrder \| None` | None on failure; else polled close fill (side=SELL). |
| `get_position` / `get_all_positions` / `get_portfolio_state` | Normalized `Position`/`PortfolioState`; qty always **positive**, direction in `side` (F54). `get_position` → None on miss; the other two raise `BrokerError`. |
| `get_open_orders(symbol?) -> list[OpenOrder]` | Flattens bracket/OCO legs (`nested=True`), dedups by id; `[]` on failure. |
| `get_fills(since?) -> list[FillEvent]` | Activity-feed fills keyed by activity id; `[]` on failure (never kills the publisher, NFR-4). |
| `get_latest_prices(symbols) -> dict` | Best-effort latest trade price; `{}` on failure/empty. |
| `is_market_open(retries=3, delay=1.0) -> bool` | Retries; **fail-closed (False)** after all retries. |
| `is_shortable(symbol) -> bool` | tradable AND shortable AND easy_to_borrow; **fail-closed**; 30-min TTL cache; transient failures NOT cached (F60). |
| `record_trade_ledger(path, since?, min_notional?)` | Appends closed round-trips via `trades_log.record_trades`. |
| `replace_order` / `cancel_all_orders` | Alpaca: native. broker_api: inherits `BaseBroker` emulation. |
| class attr `halt_reference_symbol` / `cancel_settle_wait` | Inherited defaults (`SPY` / `6.0`) — unchanged. |

## 3. What is genuinely shared (pure dedup — T1)

Byte-for-byte or trivially-identical across the two files:
- Module constants `_ALPACA_TO_ORDER_TYPE`, `_TERMINAL_STATUSES`.
- `@staticmethod _position_side(pos)` — identical.
- `@staticmethod _to_open_order(o, default_symbol)` — identical (only line-wrapping differs).
- `_poll_for_fill` — same loop; differs **only** in the per-client "get one order" call.
- `is_market_open`, `is_shortable` — identical except the client attribute (`self._client` vs `self._c`).
- `submit_order`, `close_position`, `get_order_status`, `cancel_order`, `get_position`,
  `get_all_positions`, `get_portfolio_state`, `record_trade_ledger` — same algorithm; differ only
  in which client method is called.
- `_build_request` bracket/OCO/market/limit/stop/stop-limit branches — structurally identical.

These collapse cleanly via a **template-method** base: the base owns the algorithm and calls thin
client-specific hooks (`_submit`, `_get_order`, `_cancel`, `_close`, `_open_position`,
`_all_positions`, `_account`, `_clock`, `_get_asset`, `_activities`, `_make_data_client`,
`_ledger_client`).

## 4. Genuine DIVERGENCES (not pure dedup — decide before extracting)

These are the reason a naive "lift identical methods" merge is unsafe. Each is a real behavior
difference between the two brokers today; collapsing them onto one implementation **changes one
broker's behavior** and is therefore a T2/T3 decision (see `2-tier-ledger.md`).

| # | Area | AlpacaBroker | BrokerApiBroker | If unified naively |
|---|------|--------------|-----------------|--------------------|
| D1 | **Side mapping** | `_alpaca_side`: `BUY_TO_COVER→BUY`, `SELL_SHORT→SELL`, raises on unknown | `BUY if ==BUY else SELL` → **`BUY_TO_COVER`→SELL (wrong)** | broker_api short cover/exit side flips → **behavior change (latent-bug fix)** |
| D2 | **TIF** | fail-closed map day/gtc/ioc/fok; raises on others (F9) | only gtc→GTC else→DAY (silent downgrade) | broker_api would start **rejecting** ioc/fok instead of downgrading |
| D3 | **`_build_request` extras** | `_extras` passes extended_hours/client_order_id; supports `TRAILING_STOP` | neither | broker_api gains extended_hours/client_order_id/trailing paths |
| D4 | **`get_open_orders` filter** | `status=OPEN` | `status=ALL` + client-side terminal filter (Broker-API quirk) | must stay subclass-specific (param/hook), not collapse |
| D5 | **Fill mapper** | `_to_fill_event` parses **raw dict** from `RESTClient.get` | `_to_fill_event_typed` parses **typed `TradeActivity`** + `PaginationType.FULL` | stays subclass hook `_parse_fill`; output shape identical |
| D6 | **latest-prices data client** | prod positional `StockHistoricalDataClient(key, secret)` | sandbox `use_basic_auth=True` + `url_override=…sandbox…` | stays subclass hook `_make_data_client()` |
| D7 | **portfolio account fetch** | `get_account()` | `get_trade_account_by_id(account_id)` | absorbed by `_account()` hook |
| D8 | **ledger client** | passes `self._client` directly | wraps in `_LedgerClientShim` | absorbed by `_ledger_client()` hook |
| D9 | **request classes** | from `alpaca.trading.requests` | envelopes from `alpaca.broker.requests`, legs from `alpaca.trading.requests` | request-class set must be subclass-provided |

D4–D9 are **structural** divergences absorbable by subclass hooks → still **T1** (behavior preserved).
D1–D3 are **behavioral** divergences → **T2/T3 gate** (a decision, not a mechanical move).

## 5. Current test coverage (characterization baseline)

Green baseline confirmed: `tests/test_broker_api_broker.py` + `tests/test_execution.py` +
`tests/test_kis_broker.py` → **80 passed** (at ec2875c).

| Broker | Coverage today | Gap |
|--------|----------------|-----|
| **BrokerApiBroker** | **Strong** — `test_broker_api_broker.py` covers init fail-closed, submit (market/bracket), order lifecycle, positions, portfolio, close, open-orders leg flatten, fills (typed + filter + best-effort), latest-prices (incl. lazy build-once), market clock (open/closed/fail-closed), ledger shim, mappers PBT. | none material |
| **AlpacaBroker** | **Partial** — `test_execution.py::TestAlpacaClockRetry` (retry/fail-closed) + `TestTradeLedgerPort` (delegates to record_trades). | **`_build_request` for every order type (market/limit/stop/stop-limit/bracket/OCO/trailing), `_extras` passthrough, `_alpaca_side` short-side mapping, `_time_in_force` fail-closed, `get_open_orders` leg-flatten, `_to_fill_event` dict parse, `get_latest_prices`, `is_shortable`, `replace_order`** are NOT locked. |

### Characterization gap to close in Stage 1 (after the T3 gate)
Add `AlpacaBroker`-side characterization tests mirroring `test_broker_api_broker.py`, against a
fake `TradingClient`, asserting the *current* behavior of the methods listed above — **plus**
explicit tests pinning the D1–D3 behaviors so the redesign's equivalence is checked against the
**decisions taken at the gate** (preserve vs fix), not against today's accidental behavior.

## 6. Out of scope (this track)
- `KISBroker`, `SimulatedBroker` — different families.
- `BaseBroker` contract — unchanged (defaults may not move unless D-items require it).
- Any RiskManager / executor / wiring change.
