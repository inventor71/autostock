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
