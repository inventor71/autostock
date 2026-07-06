# Business Rules

## Rules by Domain

### Order Safety (Single Risk Gate)

#### One Gate, No Exceptions
- **Rule**: Every order — from the agent, from a classic-strategy signal, or from a human
  steering command — must pass through `RiskManager.validate_order()` (or its
  `evaluate_signal`/`receive_human_order` entry points) before any broker call.
- **Rationale**: The LLM is treated as a brilliant analyst but a terrible fiduciary; it must
  never be able to touch money directly.
- **Implemented In**: `src/risk/manager.py`, invoked from `src/agent/executor.py`,
  `src/trading/engine.py`, and the console's structured order tools (via the daemon).
- **Invariants**: No code path constructs a broker order without first passing through this
  gate.

#### Bracket Buy Sizing From Actual Stop Distance
- **Rule**: For a bracket buy, quantity is sized from the *actual* resolved stop distance
  (`stop_frac = (entry - stop) / entry`), capped so the dollar risk never exceeds
  `max_portfolio_risk` regardless of how wide the stop is.
- **Rationale**: A wide ATR-based stop must not silently oversize the position; risk budget
  is the invariant, not share count.
- **Implemented In**: `src/risk/manager.py` (`_build_bracket_buy`)
- **Invariants**: Stop is floored at `entry * (1 - max_stop_distance_pct)`; target defaults
  to `entry + default_risk_reward * (entry - stop)` if the LLM didn't supply one.

#### Short Entry — Mandatory Stop (Fail-Closed)
- **Rule**: A short entry with no resolvable stop-loss is rejected outright — there is no
  market-short fallback the way there is for longs.
- **Rationale**: Short positions have theoretically unbounded loss; an unprotected short is
  never an acceptable business outcome.
- **Implemented In**: `src/risk/manager.py` (`_handle_sell_short`, `_build_bracket_short`)
- **Invariants**: Bracket short uses inverted geometry (stop ABOVE entry, target BELOW
  entry); size is derived the same way as bracket buys but from `(stop - entry) / entry`.

#### Shorting Master Switch (F60)
- **Rule**: `shorting_enabled` is a deployment-level opt-in (default False); when False, all
  short entries are rejected regardless of `force`.
- **Rationale**: The dangerous default must always be the conservative one — shorting is
  unlimited-downside and must be an explicit choice, not an emergent behavior.
- **Implemented In**: `src/risk/manager.py.__init__`, `_handle_sell_short`
- **Invariants**: Not overridable by `force=True` at the RiskManager level, including from
  human steering.

#### Squeeze Guard (F54)
- **Rule**: A stock already up ≥ `individual_stock_halt_pct` (default 10%) intraday is
  ineligible for a *new* short (existing shorts are unaffected).
- **Rationale**: Prevents adding fresh shorts into a live squeeze.
- **Implemented In**: `src/risk/manager.py` (`_handle_sell_short`)

#### Circuit Breaker (Independent Long/Short Halts)
- **Rule**: New BUYs halt when SPY day-change ≤ `market_halt_threshold_pct` (default -3%);
  new SHORTs halt independently when SPY day-change ≥ `short_market_halt_threshold_pct`
  (default +3%). The two breakers are not linked.
- **Rationale**: A falling market and a melt-up are different risk regimes for longs vs.
  shorts; conflating them would either over- or under-protect one side.
- **Implemented In**: `src/risk/manager.py` (`update_market_halt`)

#### SELL/COVER Direction Guard (SECURITY-15)
- **Rule**: A SELL signal against a SHORT position (or BUY_TO_COVER against a LONG position)
  is rejected with a clear message rather than silently doing the wrong thing.
- **Rationale**: Defense-in-depth against a signal-direction mixup accidentally flipping
  exposure.
- **Implemented In**: `src/risk/manager.py` (SELL/BUY_TO_COVER handlers)

#### Human-Order Capability Gate (F9, Fail-Closed, Not Force-Overridable)
- **Rule**: `time_in_force` must be one of day/gtc/ioc/fok; `order_class` must be one of
  simple/bracket/oco; price fields must be > 0. Protective-leg price-sanity (stop < entry <
  target for longs, inverted for shorts) is never overridable by `force`.
- **Rationale**: `force` exists to override budget/pool/breaker *soft* limits for an
  informed human, never to bypass structural safety checks.
- **Implemented In**: `src/risk/manager.py` (`receive_human_order` and its per-side helpers)
- **Invariants**: A plain buy/short with no protective legs auto-upgrades to a bracket if an
  ATR stop is resolvable (auto-protect); a short that still has no stop after auto-protect is
  rejected even with `force=True`.

#### Stop Ratchet (One-Directional Tightening)
- **Rule**: `ratchet_stop()` only tightens a resting stop (moves it toward the current price)
  unless `allow_widen=True` is explicitly passed; for LONG, tightening means moving the stop
  UP; for SHORT, moving it DOWN.
- **Rationale**: Protective stops should only ever reduce risk unless a human explicitly asks
  otherwise.
- **Implemented In**: `src/risk/manager.py` (`ratchet_stop`)

### Journal & Execution Integrity

#### Idempotent Decision Execution
- **Rule**: The executor tracks a byte cursor + a set of "terminal" decision indices
  (executed or legitimately skipped); a terminal index is final and is never reprocessed,
  even across a daemon crash/restart.
- **Rationale**: A crash mid-execution must never result in double-submitting an order.
- **Implemented In**: `src/agent/executor.py`, state in `.executor_state.json`
- **Invariants**: Reads use `read_complete_lines` (torn-safe, byte-based); if a malformed
  line is encountered during a rewrite (restamp), the rewrite refuses to proceed rather than
  silently dropping data.

#### Decision Validity Window
- **Rule**: A `Decision` with a `valid_until` in the past is skipped (`skipped_expired`)
  rather than executed.
- **Rationale**: Market conditions the LLM reasoned about may no longer hold by the time the
  executor processes a delayed decision.
- **Implemented In**: `src/agent/executor.py`

#### Protective Actions Are Never Gated
- **Rule**: Discretionary actions (BUY, SELL) can be vetoed by the steering gate when a
  symbol is locked/denied by a human; protective actions (HOLD, ADJUST_STOP, SELL_SHORT,
  BUY_TO_COVER) always execute regardless of lock/deny state.
- **Rationale**: "Every position is protected" is an invariant that must never be blocked by
  an operator's lock — a human locking a symbol should stop new entries, not disable its
  safety net.
- **Implemented In**: `src/agent/steering/gate.py`

#### Lifecycle Gating Is Scheduler-Level, Not Gate-Level
- **Rule**: `paused` suppresses all wakes; `entries_halted` drops only `entry_inducing` wake
  events (fills, protective reassessment, and stops still fire).
- **Rationale**: Halting new entries must not blind the agent to fills or protective
  triggers on positions it already holds.
- **Implemented In**: Scheduler wiring in `src/trading/modes/agent.py` / intraday wake
  detection

#### Steering Command Validation (Fail-Closed, No Silent Drop)
- **Rule**: A command must have `confirmed=True` and a valid HMAC token, or it is rejected —
  and every rejection produces a visible outcome event, never a silent drop.
- **Rationale**: A human must know immediately if their command didn't take effect.
- **Implemented In**: `src/agent/steering/channel.py`, `operator-console/src/parser.ts`

#### Token Never Logged (SECURITY-03)
- **Rule**: The steering operator token is validated and then dropped from every downstream
  log/event; `SteeringCommand.redacted()` strips it before serialization.
- **Rationale**: A single shared secret protecting the write path to a trading account must
  never leak into logs, even accidentally.
- **Implemented In**: `src/agent/steering/records.py`, `operator-console/src/mcp-server.ts`

### Self-Learning

#### Lesson Efficacy Requires a Minimum Sample
- **Rule**: A lesson's efficacy (win_rate, avg_excess) is only trusted once
  `applied_n ≥ MIN_EFFICACY_SAMPLE` (20); below that, recall (F65) does not amplify an
  unproven lesson.
- **Rationale**: Small-sample efficacy is noise, not signal; a single lucky/unlucky trade
  must not bias future prompts.
- **Implemented In**: `src/agent/learning/efficacy.py`

#### Excess Normalized by Holding Period
- **Rule**: `avg_excess` is normalized by `holding_days` so a 2-day trade and a 45-day trade
  are comparable on the same efficacy scale.
- **Rationale**: Raw excess return conflates trade duration with skill; normalizing removes
  that confound.
- **Implemented In**: `src/agent/learning/efficacy.py` / `src/agent/aggressiveness.py`

#### Aggressiveness Is a Single Knob With a Whitelisted Overlay
- **Rule**: `conservative | balanced | aggressive` merges a risk overlay only through an
  explicit allow-list of keys (`ALLOWED_RISK_KEYS`) — safety-gate keys (shorting_enabled,
  circuit breaker) are never included in the overlay.
- **Rationale**: The knob should tune posture (position sizing, grading horizon, recall
  recency weight), never unlock a safety rail.
- **Implemented In**: `src/agent/aggressiveness.py`

### Self-Authored Triggers (F88)

#### Trigger Registration Is Create-Only
- **Rule**: Re-registering an existing trigger id is an error; live `state.json` is never
  silently reset.
- **Rationale**: A trigger's fired-count/error-count history is meaningful audit state that
  must not be quietly discarded by a re-registration.
- **Implemented In**: `src/agent/triggers/store.py`

#### Predicate Sandbox Is Fail-Closed
- **Rule**: Predicate source is statically screened (no imports, no network, no file ops,
  ≤16KB) and executed with network off and `src` unmounted; 3 consecutive evaluation errors
  auto-disable the trigger with a reason.
- **Rationale**: An agent-authored predicate is untrusted code; it must be contained even if
  the agent's authoring intent was benign.
- **Implemented In**: `src/agent/triggers/sandbox.py`, `ast_screen.py`, `evaluator.py`

#### Verdict Coercion Is Strict
- **Rule**: A predicate's `fire` field must be a strict boolean (not merely truthy); `why` is
  truncated to 500 characters.
- **Rationale**: Prevents a predicate from ambiguously "firing" on a non-boolean truthy value.
- **Implemented In**: `src/agent/triggers/models.py`

#### Runaway Guard
- **Rule**: A maximum of 64 active triggers is enforced.
- **Rationale**: Bounds evaluation cost and the LLM-authored-code attack/blast surface.
- **Implemented In**: `src/agent/triggers/store.py`

### Signal Assembly

#### Fail-Honest Degradation
- **Rule**: Every research-turn data source (news, earnings, IPO, sentiment, holdings) is
  wrapped independently; a single source's failure produces an entry in `degraded_sources`
  and the brief still assembles with the remaining sections.
- **Rationale**: A missing sentiment feed should never prevent the agent from seeing movers
  and earnings; the LLM should simply be told what's missing so it can compensate.
- **Implemented In**: `src/signals/collector.py`

#### Universe/Holdings Tags Never Filter
- **Rule**: `in_universe` and `is_held` are informational tags on movers/earnings/IPOs, never
  filters — an out-of-universe mover or a pre-IPO name is still surfaced, just labeled.
- **Rationale**: Awareness of market-wide context (e.g., a pre-IPO competitor) has value even
  for names the system can't trade yet.
- **Implemented In**: `src/signals/movers.py`, `ipo_cal.py`, `earnings_cal.py`

#### Sentiment Outlier Cold-Start Guards
- **Rule**: Outlier z-scoring requires `min_baseline_points` (12) and `min_tagged` (8) before
  a symbol can qualify; points older than `max_age_minutes` (180) are dropped so a stopped
  sweep never produces stale outliers.
- **Rationale**: Small-sample sentiment ratios are unreliable; the sweep's own downtime must
  not masquerade as a live signal.
- **Implemented In**: `src/signals/sentiment.py`

### Universe Building

#### Empty/Degenerate Universe Is Fail-Closed
- **Rule**: A dynamic universe fetch that returns a degenerate result (below `_min_base()`,
  e.g. far fewer than the expected ~100 S&P constituents) is rejected in favor of the last
  good cached snapshot; the universe as a whole must never be empty.
- **Rationale**: A silently truncated universe (e.g., from a scraping failure) could cause
  the agent to systematically ignore most of the market without any visible error.
- **Implemented In**: `src/universe/base.py`, `us_provider.py`

### Provider Consistency (F92 / F94)

#### Account-Truth Reads Must Go Through the Provider Factory
- **Rule (Python, F92)**: Every code path that reads account truth (tools CLI, equity
  logging, health checks, status scripts) must call `create_broker(settings)` — none may
  hard-code `AlpacaBroker()`.
- **Rationale**: A hard-coded broker construction previously caused `account_farm`
  multi-instance deployments to read the shared Alpaca paper account instead of their own
  sub-account, producing ghost positions.
- **Implemented In**: `src/execution/brokers/factory.py`, `src/agent/tools/__main__.py`,
  `src/agent/logs/equity.py`

#### Console Account-Truth Reads Must Be Provider-Aware
- **Rule (TypeScript, F94)**: The console's account-truth read tools route by
  `broker.provider` — `alpaca` reads the live Alpaca API directly; `account_farm` reads the
  daemon's `snapshot.json` (which already reflects the correct sub-account). Market data
  (bars/quotes) always goes to Alpaca regardless of provider (account-agnostic). Under
  `account_farm`, `orders` degrades to open-only and `portfolio_history` is unsupported (with
  explicit user-facing guidance, not a silent wrong answer).
- **Rationale**: Mirrors the F92 fix on the console side — the daemon's snapshot is the only
  place that already knows the correct sub-account for a farmed instance.
- **Implemented In**: `operator-console/src/account-truth.ts`

### Production Multi-Instance Safety (F90)

#### Account Deduplication
- **Rule**: Each production instance has a unique account identifier (explicit
  `BROKER_ACCOUNT_ID` or an Alpaca key digest); the daemon refuses to start if another
  running instance is already trading that account.
- **Rationale**: Prevents two daemon processes from double-executing against the same
  brokerage account.
- **Implemented In**: `scripts/prod-run.sh` (`cmd_up`, SR-1/SR-2 checks)

#### Host-Daemon Collision Warning
- **Rule**: `prod-run.sh` warns if a non-containerized `main.py --mode agent` process appears
  to be running (may share an account with a containerized instance).
- **Rationale**: A second guard against duplicate execution outside the container namespace.
- **Implemented In**: `scripts/prod-run.sh` (SR-2)

### Eval Harness Correctness

#### Executor Replay Uses Production Code
- **Rule**: Tier-1 grading replays the agent's proposed decisions through the *real*
  `DecisionExecutor`/`RiskManager` (seeded with the scenario's held positions/prices) rather
  than a re-implementation of the rules.
- **Rationale**: A hand-written re-implementation of the risk rules for test purposes could
  drift from production behavior and give false confidence; replaying through production code
  makes that drift structurally impossible.
- **Implemented In**: `src/evals/grading.py` (`replay_through_executor`)

#### Extraction Integrity Check
- **Rule**: The raw line-count delta in `decisions.jsonl` must equal the parsed-decision
  delta after a turn; a mismatch fails the scenario outright (extraction bug), independent of
  whether the agent's behavior was otherwise correct.
- **Rationale**: A silent parsing bug (e.g., losing a malformed decision line) must be caught
  before behavior grading can even be trusted.
- **Implemented In**: `src/evals/artifacts.py`, `src/evals/grading.py`
