# Toss Securities setup

The Toss integration uses the official REST API, checked against OpenAPI **1.2.28**
on 2026-11-23. It is opt-in. Linking an account does not switch the running Alpaca
daemon or enable trading.

## Reuse an existing toss-stock connection

If `~/Project/toss-stock` already monitors your account, connect without copying its
client ID, secret or token:

```bash
venv/bin/python -m src.execution.brokers.toss.setup --from-toss-stock ~/Project/toss-stock
venv/bin/python -m src.execution.brokers.toss.setup --check
```

Autostock verifies the existing token and selected account, then saves **only the token
file path and account selection** in its private connection file. It does not read the
other project's `.env`. If toss-stock has no saved account choice, exactly one eligible
account must be returned. Failed verification preserves any previous Autostock connection.

This mode is **always read-only**, including when live writes are enabled in configuration.
The existing toss-stock monitor remains responsible for refreshing `.cache/token.json`;
Autostock rereads that file on each request and never issues or stores its own token.
Keep toss-stock's monitor running. If the token expires or is rejected, let toss-stock
refresh its connection and retry `--check`. Autostock stops with an explanation instead
of invalidating the monitor's token. Missing, malformed or insecure token files also fail
closed. No changes or restart are required in toss-stock.

Use the account and quote commands below to select Toss for an individual invocation.
The daemon's configured broker remains unchanged by account linking.

## Link your account locally

Use this standalone mode only when another program is **not** managing tokens for the
same API client. If toss-stock is already connected, use the shared connection above.

1. Sign into [Toss Securities WTS](https://tossinvest.com/). In **Settings → Open API**,
   issue a client ID and client secret. Register the **public IP of the machine running
   Autostock** in the allowed-IP list. A VPN or changing public IP can invalidate this.
2. From the repository root, run this in your own terminal:

   ```bash
   venv/bin/python -m src.execution.brokers.toss.setup
   ```

3. Paste the client ID and secret into the hidden prompts. Select the brokerage account
   if more than one is returned. The command verifies account, holdings and buying-power
   access using read-only API requests, then saves the selection.

Do not paste keys into chat, command arguments, source files or YAML. The setup command
does not need your Toss password, OTP or account number. It retrieves eligible accounts
from Toss and displays only their last four digits.

Credentials are stored as a **local plaintext file restricted to your OS user**:
`~/.config/autostock/toss/credentials.json` (directory 0700, file 0600). Token and order
state use `~/.local/state/autostock/toss/` with the same permissions. XDG directory
overrides are respected. These files stay outside Git; symlink files and insecure
permissions are rejected. They are not encrypted or restricted by a server-side read-only
token scope: the adapter's read-only switch blocks writes locally.

Check the saved connection later without entering keys again:

```bash
venv/bin/python -m src.execution.brokers.toss.setup --check
```

Re-run setup to change credentials or account. Revoke/regenerate a compromised API key
in Toss WTS; deleting a local file does not revoke the provider's credential.

## Use account and market-data tools

The following command selects Toss for **this read-only invocation only**. It does not
change the daemon's environment or configuration:

```bash
AUTOSTOCK_BROKER_PROVIDER=toss AUTOSTOCK_BROKER_PAPER=false \
  venv/bin/python -m src.agent.tools account
```

Use Toss quotes and indicators independently of the broker:

```bash
AUTOSTOCK_DATA_PROVIDER=toss venv/bin/python -m src.agent.tools quote AAPL
AUTOSTOCK_DATA_PROVIDER=toss venv/bin/python -m src.agent.tools indicators AAPL
```

In standalone mode, the shared token cache prevents concurrent daemon/tool processes from repeatedly
revoking each other's token. Run instances for the same credentials under the same
OS user and shared state directory. Separate machines must not independently mint
tokens for the same client.

## Supported behavior and differences from Alpaca

| Capability | Implementation |
|---|---|
| Account, holdings, prices and regular-session clock | Supported for the US/USD account slice |
| Ordinary orders | MARKET/LIMIT, DAY, regular US session; whole-share buys; fractional market sells up to 6 decimal places |
| Cancel | Waits for original-order cancellation; a cancel acknowledgement alone is not success |
| Replace | US limit-price changes only; retains Toss's new order ID; quantity changes rejected |
| Submission recovery | Stable `client_order_id`, persistent intent journal, no automatic retry of ambiguous writes |
| Candles | Paginated 1m/1d data; 5m/15m/30m/1h/4h resampling; completed bars only |
| KR market data | Available explicitly through `TossDataProvider(client, market="KR")`; KR trading/configuration is not enabled |
| Bracket/OCO/OTO, stops, trailing stops and shorts | Rejected by the Alpaca-shaped order adapter before submission |
| Autonomous agent mode | Blocked at startup because its required stop-market brackets are unavailable |
| WebSocket fill events and round-trip ledger | Not implemented; REST order detail reports cumulative executed quantity and average price |
| Broker paper endpoint | No documented endpoint found; `broker.paper=true` is rejected for Toss |

Toss's native OCO/OTO orders accept **limit orders only**. Translating our stop-market
brackets into those orders would change gap and execution behavior. Existing conditional
orders created in Toss must be managed there; the adapter refuses to return a misleading
complete open-order list or close a position while such orders are present.

The broker exposes **available USD cash + US holdings**, labeled
`valuation_basis=available_cash_plus_positions`. This excludes KRW assets and may exclude
reserved/unsettled funds. It is not complete account NAV, so Autostock refuses to append it
to the equity-return ledger. This prevents a reservation change from appearing as a
trading loss or gain. API US purchases do not automatically exchange KRW into USD.

Toss US data covers selected exchanges, not NBBO. Minute timestamps are converted from
bar-end to bar-start. Daily timestamps retain the local trading date; incomplete daily
bars are excluded conservatively until 16:00 New York (20:00 Seoul for KR). Adjusted
history is the provider default; instantiate with `adjusted=False` when needed, noting
Toss's documented historical raw-data limitations. No return improvement is inferred
from this integration or its contract tests.

## Live writes and recovery

The broker adapter contains live simple-order operations, but writes require **all three**
settings: `broker.paper=false`, `app.mode=live`, and `toss.read_only=false`. Defaults remain
Alpaca paper and Toss read-only. Account linking never changes these switches. Setting
them does not enable Toss autonomous agent mode or weaken its bracket requirement.

Callers must pass a stable `client_order_id` for each logical intent. Accepted orders return
their provider ID and actual filled quantity (zero while pending). Unresolved submissions
remain blocked in the private order journal, even after Toss's ten-minute idempotency
window. Inspect the actual order history in Toss before issuing a new intent; deleting
the journal to make a retry succeed can create duplicates. Reads retry bounded transient
errors; writes, modifications and cancellations do not retry automatically.

## Automatic commission refresh

`account` now includes `trading_costs`: the account-specific US rate, confirmation time,
and next check time. The `/api/v1/commissions` response is cached privately per connection
and account. Refresh is due after **6 hours or the end of the applicable KST date**, whichever
comes first. The expiry date is inclusive; `2026-11-24` stops applying at
`2026-11-25T00:00:00+09:00`. Null / `9999-12-31` expiry dates still get the six-hour refresh.
Refresh happens on use; the shadow runner checks it every polling cycle even outside
market hours. The program must be running to perform a scheduled check.

An expired schedule returned again by the API, an ambiguous schedule, or a failed refresh
does **not** fall back to the old rate or zero. New live BUY submissions are blocked;
risk-reducing live SELLs remain available. In the shadow account, all simulated fills wait
for cost confirmation and automatically resume after a successful refresh. Positions and
observations remain available, with the failure visible in `health.cost_error`.

Annual capital-gains tax is deliberately separate. The commission API does not supply all
taxes or regulatory charges: the dry model currently estimates SEC sell fees at
$20.60/million, rounded up to cents, and zero TAF for the October–December 2026 holiday.
These **dated assumptions require review after 2026-12-31**; fills pause outside their
review window. Account commission refresh is automatic; scraping unstructured pages is
not used to silently change regulatory assumptions. See the
[SEC rate advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2) and
[FINRA holiday filing](https://www.govinfo.gov/content/pkg/FR-2026-09-23/html/2026-19392.htm).
Commission rounding is conservatively upward, and the public small-order commission
waiver is not assumed for an account-specific promotion. This can overestimate small-trade
costs; each fill retains the exact rate and assumptions used.

## Multi-day dry evaluation

Use a **local shadow account fed by Toss GET quotes**. It does not create, reset or trade
an Alpaca account. Alpaca's paper simulator excludes latency slippage and regulatory
fees, and does not constrain fills by quoted quantities; see its
[paper specification](https://docs.alpaca.markets/us/docs/paper-trading).

From the repository root, initialize a new run:

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 init --days 7
```

This takes one snapshot of your US holdings (quantities and average purchase prices) and
available USD cash. It preserves the historical cost basis, but measures new performance
from the snapshot's market value. Initial existing gains/fees are not counted again.
The initial capital is a **USD slice**, not complete Toss NAV: KRW, reserved/unsettled
funds and real pending orders are not imported. Later actual trades/deposits do not change
the counterfactual account. A second `init` in the same directory is rejected.

Models, risk settings, universe, duration and daily call budget are frozen at initialization.
By default the configured US universe is unioned with the existing holdings; `--symbols
AAPL,MSFT,SPY` selects a smaller pool while retaining every held symbol. Model provider,
model IDs and efforts come from the existing settings/environment. No provider switch is
made automatically. Defaults: 7 **calendar** days, one research/intraday turn per 60 minutes,
at most 8 attempted turns per New York date. Failures and restarts count against this budget.
The first turn runs during the regular session. Multi-agent research and automatic prompt
self-rewriting are off in this comparison so its policy stays fixed.

Observe one cycle without using a model:

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 run --once
```

Run continuously with the configured trading agent:

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 run --agent
```

Keep the machine and toss-stock token monitor running. Ctrl-C stops the runner; the same
command resumes the same account and original deadline. Polling continues in parallel
while the model reasons. No new turn or order starts after the persisted deadline.
Shutdown lets an already-running model call finish within its provider timeout and does
not execute that final turn's decisions. `--seconds 60` limits a short observation run;
`--poll-seconds 5` is the default observation cadence. An agent call budget is **not** a
dollar cap or a readable Codex weekly-usage meter.

For unattended operation on this Linux host, a separate user service is optional:

```bash
systemd-run --user --unit=autostock-toss-shadow --property=WorkingDirectory="$PWD" --setenv=PATH="$PATH" \
  --property=UMask=0077 --property=Restart=on-failure \
  "$PWD/venv/bin/python" -m src.evals.toss_shadow \
  --dir "$PWD/research-comparisons/toss-shadow/trial-01" run --agent
journalctl --user -u autostock-toss-shadow -f
```

Stop with `systemctl --user stop autostock-toss-shadow`. This is independent of the existing
Autostock daemon. A second runner for the same directory is rejected. Only use the dedicated
`src.evals.toss_shadow` entry point; the ordinary agent mode rejects the shadow provider
because it would otherwise reuse the normal journal. Do not export shadow environment
overrides to the normal daemon.

Inspect results while it runs or afterwards (no API request):

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 report
```

The directory is gitignored and private (0700, state files 0600):

| Artifact | What to compare |
|---|---|
| `account.json` | Durable cash, positions, pending orders, all fills with quote evidence and cost breakdown; frozen settings and attempted turns |
| `equity.jsonl` | Periodic strategy/hold-book valuations, quote timestamps, HTTP latency and health; gaps remain visible |
| `workspace/` | Separate agent decisions, reasoning, execution outcomes and model usage logs |
| `report` output | Net marked return, same-start buy-and-hold return, excess return, maximum observed drawdown, incurred fees, execution shortfall and additional 10 bps/fill stress sensitivity |

An `executed` decision in the existing agent journal means an order was submitted; consult
`account.json` fills for actual **simulated** executions. The report's marked return includes
incurred costs; open positions have not been liquidated. `metrics.valid_snapshots`,
`health`, `agent_error_count` and `blocked_polls` distinguish a losing strategy from a broken
feed/model run. A few days can reveal excessive turnover or operational failures, but do
not establish statistically reliable superior returns.

Partial exits and protection are ordered intents: `SELL` followed by `HOLD` with a stop/target
submits the trim first, waits for its order to finish, then protects the actual remainder.
The dependency survives restarts and newer protection decisions. Existing virtual protection
shrinks as shares sell. Newly requested protection needs a fresh quote and levels beyond
the current spread; an already-crossed target must be reconsidered as an explicit exit.
`recent_fills` in the report and account tool shows the last ten actual simulated fills,
including whether they came from an entry, exit, stop or take-profit.

Generated simple market SELL quantities are rounded **down** to Toss's six-decimal share
unit at submission, in both live and shadow adapters. This preserves percentage exits from
fractional holdings without exceeding the requested quantity; less than 0.000001 shares is
rejected. BUY sizing and unsupported live protection remain unchanged. The submitted order
and its execution audit contain the normalized quantity.

Shadow execution errors retain the pending decision and retry after 30, 60, 120, 240 and
then at most once per 300 seconds. The delay survives restart; a revised decision can proceed
immediately, and expired/replaced/completed decisions clear their retry state. Waiting for an
accepted partial fill does not use this error delay, so protection still reconciles each poll.
`execution_retries` in the report/account tool shows each pending error, attempts and next
retry time. Data `health` and model-turn completion do not imply every decision executed.

`quote_quality` separates execution freshness from portfolio valuation. Every fill still
requires a source quote no older than **15 seconds**. Active orders and larger holdings are
polled first, with at most three extra reads per cycle for stale/error responses. Quotes are
never given a newer timestamp locally. A portfolio is `indicative` only when all quotes are
at most **120 seconds** old, no books failed, and stale holdings total at most **1%** of each
of the strategy and hold-book equity (including cash). Such holdings remain ineligible to
fill; worse data pauses model turns and new BUY decisions. `health.status=degraded` makes
this limited valuation visible. These bounds are valuation tolerances, not proof of price accuracy.

`quality_metrics` counts fresh/indicative/unavailable polls separately from the original
strict `metrics.valid_snapshots`. `session_performance` measures each New York trading day's
return between its first and latest fully fresh observations; `start_fill_count` tells you
whether trades already occurred before that baseline. It does not include the seed-to-open
repricing. `runtime_revisions` records when an implementation starts applying; old fills and
returns are retained. Outside market hours, quality retains its last observation's `as_of`
timestamp. No new quality or session history is inferred for earlier runs.

Execution defaults are deliberately explicit: buy at ask / sell at bid, 2 bps additional
adverse slippage, minimum one-second activation delay, maximum 15-second quote age,
10% of displayed size, partial fills and DAY entry expiry. The same timestamped liquidity
cannot be consumed again on restart. Limit orders require an executable price including
modeled slippage; a last-price touch is insufficient. Stops wait for a later observation
and fill at the available gap price. Poll interval/feed delays add to the nominal latency.
Use `init --latency-seconds`, `--slippage-bps`, `--participation`, `--interval-minutes`,
`--max-turns-per-day` for a **new** comparison run.

This remains a simulation: Toss's selected-exchange books do not reveal consolidated
liquidity, queue priority or real routing latency. Stops/OCO are local hypothetical
protection, not a capability of the live adapter. Cancels are local/immediate; USD sale
proceeds are reusable immediately, without settlement restrictions. FX, annual capital
gains tax, dividends, splits, mergers and ADR fees are not modeled. Avoid interpreting a
corporate-action window or data outage as strategy alpha. The extra-cost stress result is
a sensitivity calculation, not a replay of a different latency path.

## Verification

```bash
venv/bin/python -m pytest tests/toss -q
```

Tests use official public examples and a mock HTTP transport: no keys, paid models or
real orders. They cover account isolation, secrets, shared authentication, read-only
enforcement, partial fills, ambiguous writes, cancellation races, capability rejection,
pagination, time normalization and incomplete candles. A real-account check still requires
the owner to run the local setup command.

Sources: [API guide](https://developers.tossinvest.com/),
[canonical REST specification](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json),
[official FAQ](https://openapi.tossinvest.com/openapi-docs/faq.md).
