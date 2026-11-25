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

#### Position Sizing Rejects Non-Finite / Out-of-Range Inputs
- **Rule**: `PositionSizer.calculate_shares()` returns `0` shares — never raises, never
  silently clamps — if `price`, `portfolio.equity`, `portfolio.cash`, `stop_loss_pct`,
  `confidence`, or either configured risk cap is non-finite (`NaN`/`inf`), or if
  `stop_loss_pct <= 0`, or if `confidence` is outside `[0, 1]`.
- **Rationale**: An LLM- or feed-sourced number that is `NaN`/`inf`/out-of-range must not be
  able to expand the allocation math (e.g. a `NaN` propagating through `risk_amount /
  stop_loss_pct` could otherwise size an unbounded position); zero shares is the only safe
  default when an input can't be trusted.
- **Implemented In**: `src/risk/position_sizer.py` (`calculate_shares`)
- **Invariants**: `calculate_shares` never returns a position derived from a non-finite
  intermediate value.

#### Entry Drift Guard — Market Entry Fill Is Bounded (F96)
- **Rule**: A momentum entry submitted at MARKET has no price level of its own, so the
  decision→execution lag (research turn to fill, up to ~50 minutes) can let the fill land far
  from where the agent actually decided. The guard anchors on the LLM's explicit `entry` level
  when present, else on `ref_price` (the price stamped at decision time — see below). Once the
  current price has moved ADVERSELY past that anchor by more than `entry_drift_guard_atr * ATR`
  (default `0.5 * ATR`), the order downgrades from MARKET to a LIMIT capped at `anchor ± band`
  — bounding the worst acceptable fill. A name that ran away simply won't fill until it pulls
  back into the band. The guard is inapplicable (stays MARKET, pre-F96 behavior) when ATR is
  unavailable, there is no anchor at all, or `entry_drift_guard_atr <= 0`.
- **Rationale**: Without this guard, a market order queued during research can fill at a
  materially worse price than the one the agent reasoned about, silently changing the trade's
  risk/reward after the decision was already made.
- **Implemented In**: `src/risk/manager.py` (`_drift_guard_band`, `_build_bracket_buy`,
  `_build_bracket_short`); anchor stamped by `src/agent/orchestrator.py`
  (`AgentTradingLoop._stamp_ref_prices`)
- **Invariants**: An explicit LLM `entry` level always wins over `ref_price` as the anchor,
  even when both are present. The band boundary is exclusive — price exactly at
  `anchor ± band` stays MARKET, only strictly past it downgrades to LIMIT. A limit level is its
  own anchor and is never overwritten by a stamped `ref_price`.

#### Decision-Time `ref_price` Stamping Is Fail-Honest (F96)
- **Rule**: Between agent turns — right after the LLM writes a decision line, well before
  execution — the orchestrator stamps the then-current price onto `ref_price` for BUY/
  SELL_SHORT decisions that carry no explicit `limit` (market entries only; exits and holds are
  untouched). A missing price provider, a per-symbol fetch error, or a non-positive/non-finite/
  boolean price value simply leaves `ref_price` as `None` rather than raising or stamping junk;
  the drift guard then does not apply to that decision.
- **Rationale**: The anchor must be the price the agent decided at, not a possibly-drifted
  execution-time price — and a feed hiccup during stamping must never crash the turn loop or
  corrupt the journal with a bad anchor.
- **Implemented In**: `src/agent/orchestrator.py` (`AgentTradingLoop._stamp_ref_prices`)
- **Invariants**: An existing `ref_price` is never overwritten. The journal is re-persisted
  whenever either the guidance stamp or a `ref_price` was applied, so the anchor survives a
  daemon restart between the stamp and execution.

#### Short Entry — Mandatory Stop (Fail-Closed)
- **Rule**: A short entry with no resolvable stop-loss is rejected outright — there is no
  market-short fallback the way there is for longs.
- **Rationale**: Short positions have theoretically unbounded loss; an unprotected short is
  never an acceptable business outcome.
- **Implemented In**: `src/risk/manager.py` (`_handle_sell_short`, `_build_bracket_short`)
- **Invariants**: Bracket short uses inverted geometry (stop ABOVE entry, target BELOW
  entry); size is derived the same way as bracket buys but from `(stop - entry) / entry`. The
  F96 drift guard applies symmetrically (adverse = price running DOWN past the anchor).

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

### Trading Judgment & Model Selection (LLM Strategy / Agent)

#### Model Selection Defaults and Comparison Candidates
- **Rule**: Routine agent turns default to `claude-sonnet-5-5` at Medium reasoning effort;
  research turns default to `claude-opus-5-5` at High. `claude-fable-5-2` and OpenAI's
  `gpt-6-astra` ("Astra") are explicit comparison candidates, selectable via
  `agent.research_model`/`AUTOSTOCK_RESEARCH_MODEL` (Fable) or
  `AUTOSTOCK_AGENT_PROVIDER=openai` + `AUTOSTOCK_AGENT_MODEL`/`AUTOSTOCK_RESEARCH_MODEL=gpt-6-astra`
  (Astra). `effort`/`research_effort` are explicit per-turn parameters (`low|medium|high|xhigh|max`),
  passed on every turn including resumed and parallel research, and recorded in turn logs
  alongside the resolved model ID.
- **Rationale**: Model/effort choice is a trading-judgment decision, not an artifact of
  whichever coding-assistant default happens to be active; it must be explicit, auditable, and
  independently tunable per turn type.
- **Implemented In**: `config/config.py` (`AgentConfig`, `LLMConfig`), `src/strategy/llm/client.py`
  (`create_llm_client`, `BaseLLMClient.reasoning_effort`)
- **Invariants**: `AgentConfig` rejects a provider/model mismatch (`claude_code` provider with a
  `gpt-*` model, or `openai` provider with a `claude`/`sonnet`/`opus`/`fable` model) at config
  validation time, before any turn runs.

#### No Automatic Model Promotion
- **Rule**: A short synthetic pilot or comparison run never automatically promotes a candidate
  model (Fable, Astra, or otherwise) to the deployed default; promotion requires evidence from
  mature, non-overlapping samples, and prompt rewrites/rollbacks follow the same rule (see
  `PromptAutoImprover` below).
- **Rationale**: Small-sample or synthetic-only comparisons are not sufficient evidence to
  change what trades real capital; the bar for changing the production model/prompt must be
  higher than "one good-looking pilot."
- **Implemented In**: `src/evals/returns.py` (`paired_evidence`, `score_experiment` —
  `"No automatic promotion; multiple comparisons require a fresh holdout"` is an explicit
  reported limitation), `README.md` ("Trading judgment and research comparisons")
- **Invariants**: `paired_evidence` refuses to report a confidence interval when episodes
  overlap in time, when any episode is synthetic-only, or when there are fewer than
  `max(20, 4*block_size)` paired episodes — returning `"insufficient_evidence"`,
  `"overlapping_episodes"`, or `"synthetic_accounting_only"` instead of a number that could be
  mistaken for a promotion signal.

#### LLM Output Must Be Complete to Be Executable
- **Rule**: A Claude response whose `stop_reason != "end_turn"`, or an OpenAI response whose
  `status != "completed"` (or with empty output text), is treated as a hard failure
  (`ValueError`/`RuntimeError`) rather than a usable completion — and is never retried through
  the generic transient-failure backoff (`ValueError` is re-raised immediately in
  `_retry_with_backoff`).
- **Rationale**: A truncated/incomplete model response is not a lesser-confidence answer — it's
  not a decision at all. Retrying it as if it were a transport hiccup would waste an expensive
  generation on output that was never going to be valid.
- **Implemented In**: `src/strategy/llm/client.py` (`ClaudeClient.complete`,
  `OpenAIClient.complete`, `BaseLLMClient._retry_with_backoff`)
- **Invariants**: An incomplete OpenAI turn in the agent session discards any decisions staged
  earlier in that same turn (`OpenAIAgentSession`) rather than partially committing them.

#### Ambiguous or Non-Finite Model Output Cannot Trade
- **Rule**: `LLMStrategy._parse_llm_response` only accepts a single complete JSON object (bare,
  or the sole contents of one fenced code block) with `signal` in `{BUY, SELL, HOLD}`; it no
  longer extracts a JSON fragment from surrounding prose or falls back to keyword-scanning free
  text. `confidence`/`sell_pct`, when present, must be a finite numeric fraction in `[0, 1]`
  (not a bool, not `NaN`/`Infinity`, not a string) or the whole response is rejected. Any
  rejection — malformed JSON, multiple objects, out-of-range/non-finite numeric fields, free
  text — degrades to `{"signal": "HOLD", "confidence": 0.0}`, never to a keyword-sniffed
  BUY/SELL.
- **Rationale**: The old keyword fallback ("BUY" appears, "SELL" doesn't → treat as BUY) could
  execute an example or an explicit refusal ("Do not BUY this example: ...") as if it were the
  model's decision. Holding is always a safe default; inventing a side from prose is not.
- **Implemented In**: `src/strategy/llm/strategy.py` (`_parse_llm_response`, `_finite_json_number`)
- **Invariants**: `_coerce_float` (used elsewhere for numeric LLM fields) and the parser's own
  `parse_float`/`parse_constant` hooks reject `NaN`/`Infinity` JSON literals outright rather than
  silently accepting Python's permissive float parsing of them.

#### Prompt Auto-Improvement Requires an Actual, Non-Empty Change
- **Rule**: `PromptAutoImprover.analyze_and_improve` discards the proposed revision (returns
  `None`, no new version saved/activated) if the improvement response doesn't contain a usable
  non-empty `improved_prompt` string, or if the proposed text is identical to the current
  prompt after stripping whitespace.
- **Rationale**: "No evidence-supported revision" must result in no-op, not a spurious new
  prompt version that's byte-identical to (or emptier than) the one it's replacing — version
  history should only grow on a real change.
- **Implemented In**: `src/strategy/llm/auto_improver.py` (`analyze_and_improve`)

#### Prompt History Never Loses Shipped Versions
- **Rule**: Loading an on-disk `prompt_history.json` with an empty `versions` map does not
  stand in for (and hide) the repository's shipped prompt files (`trading_prompt_v1.txt`,
  `trading_prompt_v2.txt`); the loader backfills both from disk and sets `current_version` to
  the latest one found. An existing history that already has versions is preserved as-is
  (user-managed history is never overwritten by the backfill).
- **Rationale**: An empty/freshly-initialized history file on a new deployment must not make
  the system behave as if `v1` is the only prompt that ever existed — that would silently
  revert active guidance.
- **Implemented In**: `src/strategy/llm/prompt_manager.py` (`PromptManager._load_history`)

#### Signal Records the Actual Resolved Prompt Version, Not the Alias
- **Rule**: `LLMStrategy` records the prompt version that was *actually served* (e.g. `"v7"`)
  in signal metadata, not the alias that was requested (e.g. `"latest"`).
- **Rationale**: "latest" is not a stable identifier for after-the-fact analysis — grading and
  auditing a historical decision needs to know precisely which prompt text produced it.
- **Implemented In**: `src/strategy/llm/strategy.py` (`_resolved_prompt_version`,
  `generate_signal`)

#### Research Judgment: No False Confirmation From Repeated Indicators
- **Rule**: The research/trading prompt explicitly instructs that indicators derived from the
  same price move, or repeated headlines, are not independent confirmation — agreement among
  correlated signals does not by itself increase confidence. Headline age is surfaced as a
  freshness hint, not proof that the information is priced in (see News Freshness below).
- **Rationale**: An LLM can be fooled into over-weighting consensus that's actually one
  underlying fact restated multiple ways (three momentum indicators agreeing because they all
  derive from the same price bar; five headlines about the same event). Naming this explicitly
  in the prompt counters a known LLM reasoning failure mode.
- **Implemented In**: `src/agent/prompts.py`

### News Freshness / Priced-In Risk (F96)

#### Headline Age Is Surfaced, Never Used to Auto-Filter
- **Rule**: Every news item returned by the `news` tool carries `age_hours` (tz-safe hours
  since `published_at`, `None` if the date is missing/unparseable) and a coarse
  `priced_in_risk` flag: `"fresh"` when `age_hours <= 24`, `"elevated"` when `age_hours > 24`,
  `None` when age is unknown. The threshold is exact-boundary-inclusive on the fresh side (24.0
  hours exactly is still `"fresh"`). The flag is informational only — stale news is still
  returned, just labeled, mirroring the universe/holdings "tags never filter" rule.
- **Rationale**: A day-old catalyst can already be priced into the move, and the agent should
  weigh a 2-hour-old headline differently from a 40-hour-old one — but the system should never
  unilaterally decide a headline is too old to show.
- **Implemented In**: `src/agent/tools/market.py` (`_news_age_hours`, `_priced_in_risk`, `news`)
- **Invariants**: A naive/aware timezone mismatch between `published_at` and the comparison
  clock is aligned before subtraction rather than raising; a missing `published_at` always
  yields `age_hours=None` and `priced_in_risk=None`, never a default/guessed age.

### Toss Broker Integration (F100-F104)

#### Toss Live Trading Is Read-Only Unless Explicitly Opted In
- **Rule**: `TossClient`/`TossBroker` default to read-only; any write (submit/cancel/replace
  order, close position) raises unless `toss.read_only=false` AND `app.mode=live` are both
  set. A shared-token credential (F101, reused from the external `toss-stock` app) is *always*
  forced read-only — `TossClient.__init__` raises if `shared_token_file` is set and
  `read_only` is not True, because Autostock has no business minting writes on a token it
  doesn't own the lifecycle of.
- **Rationale**: A second live-broker integration must not become a second way to
  accidentally place real orders; the dangerous capability (writes) must be opt-in twice over
  (config flag + app mode), and never available at all when borrowing someone else's token.
- **Implemented In**: `src/execution/brokers/toss/client.py` (`__init__`), `broker.py`
  (`_write_enabled`), `factory.py` (`create_toss_client`)
- **Invariants**: A shared-token client can never be constructed in write-enabled mode.

#### Toss Live Order Capability Is Narrower Than Alpaca/KIS (Fail-Closed on the Gap)
- **Rule**: `TossBroker.validate_order()` accepts only MARKET/LIMIT orders, DAY time-in-force,
  regular-session hours, whole-share buys, and fractional sells floored to 6 decimals; it
  rejects BRACKET/OCO/OTO order classes, shorting, and extended hours outright rather than
  approximating them.
- **Rationale**: Toss's own OCO semantics (cancel-sibling-on-*trigger*, not on-*fill*) are not
  equivalent to the stop-market bracket model the rest of the codebase assumes; silently
  mapping one onto the other could leave a position unprotected or double-protected.
- **Implemented In**: `src/execution/brokers/toss/broker.py` (`validate_order`)
- **Invariants**: If any resting Toss conditional (OCO/stop) order is found on the account,
  `get_open_orders()`/`get_conditional_orders()` raise rather than silently returning an
  incomplete view the rest of the system might act on.

#### Fractional Market-Sell Quantities Are Floored, Never Rounded Up (F104)
- **Rule**: `normalize_market_sell()` floors a fractional MARKET sell quantity to
  `Decimal("0.000001")` (6 decimals) using `ROUND_DOWN`; if the floored quantity drops to zero
  it raises rather than submitting a zero-share order.
- **Rationale**: The shared `RiskManager`/position sizer computes quantities at higher
  (9-digit) precision than Toss's 6-decimal order granularity accepts; rounding up could sell
  more shares than are actually held, while flooring at the broker boundary keeps the shared
  risk-sizing code untouched and simply clamps at the last mile.
- **Implemented In**: `src/execution/brokers/toss/broker.py` (`normalize_market_sell`),
  mirrored in `src/execution/brokers/toss/shadow.py`'s order matching
- **Invariants**: The RiskManager's own precision/rounding behavior is unchanged for
  Alpaca/KIS; only the Toss order-submission boundary clamps.

#### Durable Order Intent Survives a Crash Between Submit and Response (F101/F104)
- **Rule**: `TossClient.create_order()` persists the `{clientOrderId → fingerprint,
  submitted_at, response}` intent record *before* issuing the HTTP POST. On restart, a
  previously-recorded intent with a matching fingerprint returns the cached response (no
  resubmission); a mismatched fingerprint for the same id raises (refuses to reuse an id for a
  different order); an intent with no recorded response yet (crashed mid-flight) blocks any
  new submission under that id until reconciled.
- **Rationale**: Order-placement POSTs are not safely retryable against a real brokerage;
  losing track of "did that order actually go through" after a crash must never result in
  either a silent lost order or an accidental duplicate.
- **Implemented In**: `src/execution/brokers/toss/client.py` (`create_order`)

#### Protective Legs Scale to Actual Filled/Remaining Quantity, Not the Original Order (F103)
- **Rule**: In `TossShadowBroker`, when a bracket entry fills, the stop-loss/take-profit legs
  are sized from the *actual filled quantity*, not the originally submitted order quantity;
  when a manual trim sell reduces a position, all resting protective legs on that symbol are
  scaled down proportionally to the *actual remaining* holding.
- **Rationale**: A partial fill or a manual trim that leaves protective orders sized to the
  pre-trim quantity could either over-sell on exit (protecting shares no longer held) or
  under-protect (leaving part of the position naked) — both silently wrong outcomes that F103
  fixed.
- **Implemented In**: `src/execution/brokers/toss/shadow.py` (bracket-fill and trim-sell
  handling in the fill/match path)

#### Shadow Account Is Seeded Once, Never Re-Mirrored From the Live Account (F102)
- **Rule**: `TossShadowBroker.initialize()` seeds the durable shadow ledger's positions/cash
  from the live Toss account exactly once; subsequent real deposits or real trades on the live
  account are explicitly NOT mirrored into the shadow ledger afterward (an assumption recorded
  in the ledger's own `assumptions` list).
- **Rationale**: The shadow account exists to answer "how would the agent have traded this
  book," which requires a frozen starting point — continuously re-syncing from a live account
  that a human might also be trading would make the comparison meaningless.
- **Implemented In**: `src/execution/brokers/toss/shadow.py` (`initialize`)

#### Commission/Fee Assumptions Are Explicitly Time-Bounded (Fail-Closed on Staleness) (F102/F105)
- **Rule**: `TossCosts.profile()` hardcodes the SEC sell-tax rate and related fee assumptions
  as valid only through a fixed review date (Q4 2026); calling it outside that window raises
  `BrokerError` rather than silently continuing to use an assumption that may no longer be
  accurate. The live commission *rate* itself is separately fetched and cached with a 6-hour
  TTL expiring at KST midnight, and fails closed (raises) if zero or more than one matching
  rate row exists for the market+date.
- **Rationale**: Regulatory fee rates and broker commission schedules change; a cost model
  that silently keeps using an expired assumption would misprice every subsequent simulated or
  real fill without any visible warning.
- **Implemented In**: `src/execution/brokers/toss/costs.py` (`CommissionSchedule.get`,
  `TossCosts.profile`)

#### Quote-Quality Gate Blocks BUY Decisions on Stale Valuation (F102/F105)
- **Rule**: The shadow account's valuation is only considered usable when ≥99% of portfolio
  value is backed by a quote fresher than 120 seconds (`fresh_value_pct` ≥ threshold); when it
  isn't, `quote_quality.valuation_usable=false` and `src/evals/toss_shadow.py`'s
  `ShadowExecutor` blocks new BUY decisions outright (existing positions/exits are unaffected).
- **Rationale**: Deciding to buy more based on a valuation computed from stale quotes could
  compound an already-wrong picture of available buying power; blocking new entries (not
  exits) mirrors the same asymmetry as the production circuit breaker.
- **Implemented In**: `src/execution/brokers/toss/quality.py` (`quote_quality`),
  `src/evals/toss_shadow.py` (`ShadowExecutor`)

#### Persistent Decisions Retry With Exponential Backoff, Not Indefinitely or Instantly (F104)
- **Rule**: A shadow decision that fails to execute is retried with
  `delay = min(300s, 30 * 2^min(attempts-1, 4))` backoff rather than being retried every poll
  tick or abandoned after one failure; the retry record is cleared on success or once the
  decision's validity window has expired.
- **Rationale**: A transient quote/orderbook hiccup shouldn't permanently drop a decision, but
  hammering a failing decision every few seconds wastes cycles and can mask a real, persistent
  problem (e.g., a quantity that will never be valid) behind log noise.
- **Implemented In**: `src/evals/toss_shadow.py` (`ShadowExecutor._record_retry`)

### Shared Research Context Freshness (F105)

#### News Fetch Failure Is Never Indistinguishable From "No News"
- **Rule**: `fetch_news()` (and the underlying provider) turns any fetch exception into an
  explicit `NewsResult(status="unavailable", errors=[...])`, never a silently-empty `items`
  list; an empty-but-successful fetch is `status="ok", items=[]`, a distinct, equally
  explicit outcome.
- **Rationale**: Before F105, an exception during news fetch was indistinguishable from "this
  symbol genuinely has no recent news" — the agent (and a human reviewing the brief) had no
  way to tell "nothing happened" from "we don't know."
- **Implemented In**: `src/data/news.py` (`fetch_news`, `NewsResult`),
  `src/data/providers/news_provider.py` (raises instead of returning `[]` on error)
- **Invariants**: Error detail recorded is the exception *type*, not its message text, to
  avoid leaking credentials/URLs embedded in a provider error into logs/prompts.

#### Fallback News Provider Never Relabels Old Content as Fresh
- **Rule**: `FallbackNewsProvider` only consults its secondary provider when the primary
  returned nothing, or only content older than 24 hours; if the primary already has recent
  (<24h) content, the fallback is never called. If the primary returned old content and the
  fallback also returns nothing newer, the original old content is kept (with its true
  publication time) rather than treated as if the fallback's absence proves it's current.
- **Rationale**: A cascading fallback must not accidentally launder a stale headline into
  looking fresh just because a second provider had nothing better to offer.
- **Implemented In**: `src/data/news.py` (`FallbackNewsProvider`)

#### Source Timestamp Is Never Overwritten by Retrieval Time
- **Rule**: Every quote/bar/news fact threaded through `src/data/freshness.py` carries its
  provider-native `source_as_of` (when the exchange/publisher generated the data) completely
  separately from `retrieved_at` (when Autostock's cache last fetched it); a cache hit never
  updates `source_as_of` to "now."
- **Rationale**: Conflating "when we last checked" with "how current the data actually is"
  would make a day-old cached price look as current as a live tick, defeating every staleness
  check built on top of it (news freshness, drift guard anchoring, quote quality).
- **Implemented In**: `src/data/freshness.py` (`latest_quote`, `bar_metadata`, `age_seconds`)

#### Unchecked or Stale Data Is "Unknown," Never Treated as "No Change" (F105)
- **Rule**: The intraday prompt (`src/agent/prompts.py`) explicitly instructs that
  unrefreshed, unavailable, or stale data in the brief is unknown — not evidence a prior thesis
  is still valid — and directs the model to state remaining material gaps rather than
  proceeding as if the picture were complete; a well-supported no-trade on incomplete data
  remains an explicitly valid outcome.
- **Rationale**: An LLM given a brief with silent gaps can over-interpret "I wasn't told
  anything changed" as "nothing changed," which is a different (and riskier) claim; naming the
  distinction in the prompt counters that failure mode the same way the F96 "repeated
  indicators aren't independent confirmation" guidance does.
- **Implemented In**: `src/agent/prompts.py` (`intraday_prompt`)

#### Shared Context Assembly Is Identical for the Normal Daemon and the Toss Shadow Runner
- **Rule**: `IntradayContext.build()` is the single implementation of "assemble bars + quotes
  + news + account snapshot + watchlist for this turn," consumed via
  `orchestrator.py`'s `intraday_brief_provider` hook by both the steering-enabled normal daemon
  (`src/trading/modes/agent.py`) and the steering-less Toss shadow runner (via
  `broker_snapshot()` standing in for the steering snapshot) — there is exactly one
  implementation of this assembly, not two drifting copies.
- **Rationale**: F105 was explicitly scoped to fix the shared path so the same bug (or future
  fix) can't silently apply to only one of the two trading modes.
- **Implemented In**: `src/agent/intraday/context.py`, `src/agent/orchestrator.py`
  (`intraday_brief_provider`), `src/trading/modes/agent.py`, `src/evals/toss_shadow.py`

#### Research Data Gaps Are Reported, Not Silently Absorbed
- **Rule**: `src/monitoring/research.py:read_context_summary()` reduces the last persisted
  `research-context.json` into an explicit `status: "ok"|"degraded"` report naming exactly
  which symbols had a news/price/bar gap, which quotes were stale (>60s) or had an unparseable
  timestamp, which watchlist symbols weren't refreshed, and whether the account snapshot
  itself failed — scoped explicitly as "last intraday context, not process health" so it is
  never confused with the broker/risk/LLM health dimensions.
- **Rationale**: A data-quality problem in the research inputs is a different failure class
  from "is the process alive" and deserves its own visible, separately-labeled signal rather
  than being folded into (and diluting) general health status.
- **Implemented In**: `src/monitoring/research.py` (`read_context_summary`)

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

#### Non-Finite or Repeated-Citation Outcomes Cannot Bias Learning
- **Rule**: An outcome with a non-finite `excess` (`NaN`/`±Infinity`) contributes zero to a
  cited lesson's `applied_n`/`avg_excess` (as if never applied). Citing the same `lesson_id`
  multiple times within one decision still counts as exactly one application
  (`applied_counts`/`lesson_efficacy` dedupe per-decision, not per-citation).
- **Rationale**: A single decision that lists a lesson 30 times, or an outcome whose excess
  computation blew up to `NaN`, must not be able to inflate or corrupt a lesson's trusted
  sample size or its average efficacy.
- **Implemented In**: `src/agent/learning/efficacy.py` (`applied_counts`, `lesson_efficacy`)

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

#### Toss Provider/Name/Mode Consistency Is Checked at the Factory, Not Assumed
- **Rule**: `create_broker()` rejects a `broker.name="toss"` configuration whose
  `broker.provider` isn't also Toss-flavored (refuses to silently fall back to Alpaca), and
  separately rejects constructing a live-write `TossBroker` (`provider="toss"`) unless
  `app.mode != "live"` is false (i.e., live mode is actually set) — while `provider="toss_shadow"`
  requires the opposite (`app.mode != "live"`, paper-only, a configured `run_dir`).
- **Rationale**: The live-vs-shadow Toss paths have inverted mode requirements (one *requires*
  live mode, the other *forbids* it); catching a mismatch at factory construction time rather
  than at first order submission prevents a misconfigured instance from running for hours
  before the gap is discovered.
- **Implemented In**: `src/execution/brokers/factory.py` (`create_broker`,
  `create_toss_client`)

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

### Performance Reporting (F97)

#### Agent-vs-S&P500 Headline Is Read-Time, Baseline-From-First-Benchmarked-Day
- **Rule**: `compute_performance()` derives the "agent vs SPY buy-and-hold" headline purely by
  reading existing `equity.jsonl` records — it persists nothing new and never touches the EOD
  pipeline. A record is *usable* only if it has both a strictly-positive `equity` AND a
  strictly-positive `benchmark.SPY` mark; the baseline (`since_date`) is the first *usable*
  record, so early lines written before the benchmark was captured are skipped rather than
  corrupting the baseline with a missing/zero SPY mark. Cumulative return is a ratio to the
  baseline price (`last/base - 1`), making it independent of starting capital. `alpha_pct` is
  exactly `agent_return_pct - spy_return_pct` (both already rounded to 2dp); `day_*` fields
  (today's delta) are present only when ≥ 2 usable records exist, else `None`.
- **Rationale**: The scorecard must answer "had I put the same money in SPY instead" without
  risking any corruption of the production equity log, and must fail honest (return `None`)
  rather than report a misleading number when the benchmark data isn't there yet.
- **Implemented In**: `src/agent/logs/performance.py` (`compute_performance`, `load_performance`)
- **Invariants**: Returns `None` (never raises, never a fabricated 0) when there are zero
  usable records, when `equity <= 0`, or when no record has a usable SPY mark at all.
  Malformed records (non-dict, non-numeric equity, non-positive/zero benchmark mark) are
  skipped individually rather than failing the whole computation. The result is invariant to
  uniformly scaling either the equity series or the SPY series by any positive constant
  (so a currency/split-adjustment-style rescale cannot change the reported return or alpha).

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

#### Return Evaluation Never Lets a Model See Future Bars
- **Rule**: `evaluate_returns()` (F97/returns harness) validates that the hidden `OutcomePath`
  matches the scenario's identity and information cutoff (`as_of`) exactly, that every future
  bar strictly follows the cutoff with no overlaps, and that every symbol/benchmark shares
  identical bar intervals; a forward-kind outcome additionally requires the recorded decisions'
  SHA-256 and `finished_at` timestamp to prove the decisions were committed before the future
  prices existed. Corporate actions (splits/dividends) in the window make the episode
  unscorable rather than silently mis-accounted. Repeated generations of the same case are
  averaged before bootstrap evidence is computed — they are not treated as independent market
  samples.
- **Rationale**: A backtest-style evaluator is only trustworthy if it is structurally
  impossible for the scored decisions to have been influenced by the very prices being used to
  grade them, and if repetition can't masquerade as additional independent evidence.
- **Implemented In**: `src/evals/returns.py` (`OutcomePath.aligned_future`, `evaluate_returns`,
  `score_experiment`, `paired_evidence`)
- **Invariants**: `score_experiment` records a `replay_source_sha256` of every file in the
  production replay path (risk manager, position sizer, executor, simulated broker,
  aggressiveness, `main.py`) alongside the report, so a scored result is traceable to the exact
  production code that produced it.
