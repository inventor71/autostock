# Stage 3 — Redesign: `AlpacaShapedBroker` template-method base

**Track**: R3 · **Date**: 2026-06-06 · **Tier**: fully T1 (preserve-all decision)

## Target structure
```
src/execution/brokers/
  _alpaca_shaped.py   NEW — AlpacaShapedBroker(BaseBroker): shared algorithm + abstract hooks
  alpaca_broker.py    AlpacaBroker(AlpacaShapedBroker): Trading-API hooks + request classes
  broker_api_broker.py BrokerApiBroker(AlpacaShapedBroker): Broker-API hooks + request classes + shim
```
The base owns every method whose *algorithm* is shared; subclasses provide only client-specific
calls and the SDK request-class set. **No public (`BaseBroker`) signature changes.**

## Hook contract (what each subclass must provide)
Abstract / overridable members the base calls:

| Member | Kind | AlpacaBroker | BrokerApiBroker |
|--------|------|--------------|-----------------|
| `_REQ` request classes (Market/Limit/Stop/StopLimit/[Trailing]) + `TakeProfit`/`StopLoss`/`GetOrders`/enums | class attrs | `alpaca.trading.requests` | `alpaca.broker.requests` envelopes + `alpaca.trading.requests` legs |
| `_alpaca_side(side)` | method | full `_alpaca_side` (BUY/BUY_TO_COVER→BUY, SELL/SELL_SHORT→SELL, raise) | current `BUY if ==BUY else SELL` (**bug preserved**, T3-1) |
| `_time_in_force(order)` | method | F9 fail-closed map (day/gtc/ioc/fok) | gtc→GTC else→DAY (**preserved**, T3-2) |
| `_extras(order)` | method | extended_hours/client_order_id passthrough | `{}` (**preserved**, T3-3) |
| `_supports_trailing` | class attr | `True` | `False` |
| `_submit(request)` | method | `client.submit_order(request)` | `c.submit_order_for_account(account_id, request)` |
| `_get_order(order_id)` | method | `client.get_order_by_id(id)` | `c.get_order_for_account_by_id(account_id, id)` |
| `_cancel(order_id)` | method | `client.cancel_order_by_id(id)` | `c.cancel_order_for_account_by_id(account_id, id)` |
| `_close(symbol)` | method | `client.close_position(symbol)` | `c.close_position_for_account(account_id, symbol)` |
| `_open_position(symbol)` | method | `client.get_open_position(symbol)` | `c.get_open_position_for_account(account_id, symbol)` |
| `_all_positions()` | method | `client.get_all_positions()` | `c.get_all_positions_for_account(account_id)` |
| `_account()` | method | `client.get_account()` (D7) | `c.get_trade_account_by_id(account_id)` |
| `_orders(filter)` | method | `client.get_orders(filter=filter)` | `c.get_orders_for_account(account_id, filter=filter)` |
| `_open_orders_status` | class attr | `QueryOrderStatus.OPEN` (D4) | `QueryOrderStatus.ALL` |
| `_open_orders_skip_terminal` | class attr | `False` | `True` (client-side terminal filter) |
| `_clock()` | method | `client.get_clock()` | `c.get_clock()` |
| `_get_asset(sym)` | method | `client.get_asset(sym)` | `c.get_asset(sym)` |
| `_make_data_client()` | method | prod positional `StockHistoricalDataClient(key,secret)` (D6) | sandbox basic-auth + url_override |
| `_fetch_fills(since)` | method | raw `client.get("/account/activities", params)` → list[dict] | typed `c.get_account_activities(...)` |
| `_parse_fill(activity)` | static | `_to_fill_event` (dict, D5) | `_to_fill_event_typed` (TradeActivity) |
| `_ledger_client()` | method | `self._client` (D8) | `_LedgerClientShim(self._c, account_id)` |
| `replace_order` / `cancel_all_orders` | override | AlpacaBroker keeps native overrides; base does NOT define them (BrokerApiBroker keeps inheriting `BaseBroker` emulation) | — |

### Methods that move to the base verbatim (algorithm only)
`_poll_for_fill`, `submit_order`, `close_position`, `get_order_status`, `cancel_order`,
`get_position`, `get_all_positions`, `get_portfolio_state`, `is_market_open`, `is_shortable`,
`get_open_orders`, `get_fills`, `get_latest_prices`, `record_trade_ledger`, `_build_request`,
`_to_open_order`, `_position_side`, module constants `_ALPACA_TO_ORDER_TYPE`, `_TERMINAL_STATUSES`.

### Equivalence argument (why behavior is preserved)
Each moved method's body is byte-identical between the two brokers **except** the client-call
expression, which becomes a hook call returning the same object the inline call returned. The 3
behavioral divergences (T3-1/2/3) are explicitly routed through subclass-provided hooks that return
each broker's *current* value. Therefore for every input, every broker produces the identical SDK
request, the identical sequence of client calls, and the identical return/exception — verified by
the existing `test_broker_api_broker.py` (broker_api side) and the new Alpaca-side characterization
tests (Alpaca side), both run before and after.

> Note the one subtlety: `submit_order` side step. AlpacaBroker currently calls `self._alpaca_side`;
> BrokerApiBroker inlines `AlpacaSide.BUY if order.side==OrderSide.BUY else AlpacaSide.SELL`. The base
> will call `self._alpaca_side(order.side)`; BrokerApiBroker's `_alpaca_side` override reproduces its
> inline expression exactly (incl. the BUY_TO_COVER→SELL bug) → no behavior change. R7 flips it later.

## Migration order (each step keeps the full broker suite green)
1. Add `_alpaca_shaped.py` with `AlpacaShapedBroker` + abstract hooks; move the two module constants
   + the two pure staticmethods (`_position_side`, `_to_open_order`) there.
2. Re-point `AlpacaBroker` to subclass it: implement Alpaca hooks, delete the now-duplicated bodies,
   keep `replace_order`/`cancel_all_orders`/`_alpaca_side`/`_extras`/`_tif`. Run broker suite.
3. Re-point `BrokerApiBroker` likewise: implement Broker-API hooks + `_alpaca_side`/`_time_in_force`/
   `_extras={}` overrides + `_LedgerClientShim`. Run broker suite.
4. Move the genuinely-shared method bodies up into the base; delete from both subclasses. Run suite
   after each method group (orders / positions / fills / market-data).
5. Full `pytest tests/` green; ruff/format; verify no other module imported a now-moved symbol.

## Risk / rollback
- Lowest-risk seam = the hooks. If a moved method misbehaves, the failing characterization test
  names the exact method; revert that one move.
- Import surface: `from src.execution.brokers.alpaca_broker import AlpacaBroker, TradingClient`
  (used by `test_execution.py`) and any `_ALPACA_TO_ORDER_TYPE`/`_TERMINAL_STATUSES` external import
  must keep resolving — re-export from the original modules if anything imports them. (Grep showed
  only intra-file use, but verify.)
