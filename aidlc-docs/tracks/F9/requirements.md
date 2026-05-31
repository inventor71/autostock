# F9 — Requirements (Alpaca-shaped gated order tools)

> Depth: Standard/Comprehensive. Derived from `requirements-questions.md` v3 answers
> (Q1=A, Q2=A, Q3=A, Q4=B, Q5=A, Q6=A, security=A, PBT=B) and the verified current
> architecture. Single writer = F9 worktree session. Awaiting user approval.

## 1. Intent

Replace the operator console's **single slash-string** order interface with **structured,
Alpaca-MCP-shaped tool calls** that still pass the daemon's **RiskManager→Broker gate**. The
operator speaks NL to the opencode console AI; the AI emits structured tool calls (understanding
slash strings only as conversational shorthand). The gate either places order(s) or returns a
structured reject. advisor-only research/intraday/PM agents are untouched.

## 2. Functional Requirements

- **FR-1 — Structured Alpaca-shaped mutating tools.** The operator-console MCP server
  (`operator-console/src/mcp-server.ts`) exposes structured tools whose **names + signatures
  mirror Alpaca MCP 1:1** (Q6=A). Scope = **stock order lifecycle only** (Q1=A):
  `place_stock_order`, `cancel_order_by_id`, `cancel_all_orders`, `replace_order_by_id`,
  `close_position`, `close_all_positions`. (Crypto/options/account/watchlist = OUT, §5.)
- **FR-2 — HYBRID: order verbs → structured tools; safety/lifecycle verbs stay deterministic.**
  (Revises Q4=B after critic review — `parser.ts:99-100,156-162` is the *only* thing that
  deterministically maps `/kill`/`/halt_entries`/`/flatten`/`/pause` to their verbs and stamps the
  `destructive`→`CONFIRM` gate; routing those through LLM interpretation loses that guarantee.)
  - **Order verbs** (`place_stock_order` etc.) become structured Alpaca-shaped MCP tools; the
    order/trade grammar is **removed** from `parser.ts`.
  - **Safety/lifecycle/approval/lock/context verbs** (`pause`/`resume`/`halt_entries`/
    `allow_entries`/`kill`/`flatten`/`approve`/`reject`/`unlock`/`note`/`directive`/
    `directive_clear`/`answer`) keep a **deterministic, model-free path**: either a thin
    verb-name tool that takes the verb directly, or the retained non-order portion of `parser.ts`.
    The `destructive` flag (`DESTRUCTIVE_VERBS`) and the `CONFIRM`-keyword gate for `kill`/
    `flatten` are preserved. `intArg` strict-digit validation for `approve`/`reject` ids is kept.
  - Slash strings remain shorthand the opencode AI understands, but emergency verbs are NOT left
    to LLM interpretation alone. `parser.ts` is **trimmed, not deleted**.
- **FR-3 — `place_stock_order` full parameter set.** symbol, side, `qty` | `notional`,
  `order_type` (market | limit | stop | stop_limit | trailing_stop), `time_in_force`
  (day | gtc | ioc | fok | opg | cls), `limit_price`, `stop_price`, `trail_price`,
  `trail_percent`, `extended_hours`, `client_order_id`, `order_class`
  (simple | bracket | oco | oto), `take_profit`, `stop_loss`.
  **Scope reality (critic-verified):** this is a real `Order`-model + broker build, NOT a field
  add. Today `OrderType` = market/limit/stop/stop_limit only (`types.py:17-21`, no
  trailing_stop); `OrderClass` = simple/bracket/oco only (`types.py:34-36`, no oto); `Order` has
  no `notional`/`extended_hours`/`client_order_id`/`trail_*` (`models.py`). U-RISK adds the enum
  members, pydantic fields + validators, and the alpaca-py request types (incl.
  `TrailingStopOrderRequest`).
  **TIF fail-closed (fixes latent bug):** `_time_in_force` (`alpaca_broker.py:131-136`) currently
  collapses any non-"gtc" TIF to `DAY` — silently swallowing ioc/fok/opg/cls. F9 makes any TIF
  not yet wired an **explicit reject**, never a silent downgrade (NFR-2 / SECURITY-15).
- **FR-4 — Human confirm preserved.** Every mutating tool is gated by opencode's permission
  `ask` (human confirms BEFORE the file-drop write), exactly as the current `steer` tool. The
  console AI proposes; it cannot place an order autonomously. Read path (`steer_read`) unchanged.
- **FR-5 — RiskManager reception = validator + auto-protect hybrid (NET-NEW for the human path).**
  (Q2=A) **Critic-verified gap:** the *agent* path runs `RiskManager.evaluate_signal`
  (`executor.py:167`) which enforces `max_open_positions`, no-add-to-existing,
  `position_sizer.calculate_shares`, and the `_new_buys_halted` circuit breaker. The *human* path
  (`build_human_buy` / `_v_buy`, `commands.py:37-62,150-167`) does **none** of that — it only
  floors qty and attaches a stop, then submits. So FR-5's budget/pool/breaker checks are **new
  logic for human orders**, not "reuse the existing gate." On a fully-specified structured order
  the daemon gate:
  1. **Respects** caller-specified order_type / prices / TIF / order_class.
  2. **Checks budget/pool/breaker** (NEW): `max_open_positions`, no-add-to-existing,
     risk-budget sizing, and `_new_buys_halted` are evaluated for human orders too.
  3. **Rejects or clamps** when qty/notional exceeds the risk budget / pool constraint.
  4. **Auto-attaches** ATR/level-based protection (bracket/OCO stop+target) when `stop_loss` /
     `take_profit` are omitted — preserving the "every position is protected" invariant.
  5. **Rejects** on price-sanity violations (long stop at/above market, unrealistically far
     limit, wrong-side prices, etc.).
  Result: order(s) submitted to the broker, OR a structured reject.
- **FR-5a — Operator override (explicit, confirmed).** Per user decision, the operator MAY
  override the budget/pool/breaker checks (FR-5 step 2) with an **explicit override flag** (e.g.
  `force=true`) — the order then still passes price-sanity (FR-5 step 5) and auto-protection
  (step 4), and the override is recorded in the human-directives log. Default (no flag) =
  fail-closed reject on violation. The override is operator-only (advisor agents never reach this
  surface, NFR-1) and still requires the opencode `ask` human-confirm (FR-4).
- **FR-6 — Structured reject/clamp feedback.** (Q3=A) A reject/clamp returns a structured reason
  code + human-readable message and, when computable, a **pass-able suggestion** (e.g. "qty
  100→37 fits the risk budget"), surfaced through the MCP tool result so the console AI can
  explain it and offer a corrected retry.
- **FR-7 — notional × non-market constraint (fail-closed).** (Q5=A) `notional` is accepted only
  for `market` + `day`; `limit`/`stop`/`stop_limit`/`trailing_stop` require an integer `qty`.
  Any other combination is a **structured reject** (no silent auto-conversion).
- **FR-8 — Order management (more net-new than first stated).** Critic-verified: `BaseBroker`
  (`execution/base.py`) has only single-target `cancel_order` / `close_position` /
  `get_open_orders`. `cancel_all` and `close_all` are emulated today by **looping**
  (`commands.py:313-314,130-135`); there is **no** broker `replace_order`, `cancel_all_orders`, or
  `close_all_positions` primitive. So `replace_order_by_id` (NEW), `cancel_all_orders`,
  `close_all_positions` need real broker methods (or explicit loop-emulation with leg-aware
  handling). `replace_order_by_id` against resting bracket/OCO legs is genuinely hard
  (`get_open_orders` flattens nested legs, `alpaca_broker.py:245-271`, with no leg-aware replace)
  and its semantics must be resolved in Application Design, not deferred (it gates whether
  `replace` is shippable in F9).

## 3. Non-Functional Requirements

- **NFR-1 — advisor-only invariant (defense-in-depth, not a single structural fact).** The new
  structured mutating tools are reachable ONLY from the operator console (opencode,
  human-confirmed). research/intraday/PM agents keep the `decisions.jsonl → DecisionExecutor →
  RiskManager` path and do NOT gain these tools. Critic-verified: the barrier is **layered** — (a)
  agents are `claude -p` subprocesses never given this MCP; (b) the operator token is scrubbed
  from agent env (`security.py:scrub_agent_env`); (c) a PreToolUse deny-hook blocks writes outside
  the agent workspace (`security.py:evaluate`); (d) the daemon rejects any command failing the
  token check (`channel.py:104`). F9 adds **no new agent-reachable surface**, preserving the
  invariant — but the design must keep verifying these load-bearing runtime steps (hook
  registration + per-spawn token scrub) after the gate refactor (BR-1 / BR-10.4 unchanged).
- **NFR-2 — Security baseline (Enabled).** SECURITY-11 (order/auth authority isolation),
  SECURITY-03 (operator token NEVER logged/echoed in tool results or events), SECURITY-15
  (fail-closed on missing token / invalid args / risk reject), SECURITY-13 (safe-deserialize
  structured args). **zod schema validation at the MCP boundary** is the explicit replacement
  for the removed deterministic parser's input-validation role.
- **NFR-3 — Cross-language contract must gain per-verb args coverage.** Critic-verified weakness:
  the current golden contract pins only the **envelope + verb/event enums** (`contract.test.ts`
  tests 27-52; `args` is `dict[str,Any]`, `records.py:52`), and the per-verb args are covered by
  `parser.test.ts` (`contract.test.ts:6`) — which the FR-2 trim removes for order verbs. So the
  contract must be **extended to pin the `place_stock_order` (and other order-verb) args shape
  across TS↔pydantic** (e.g. generate the zod schema from the pydantic models, or add a per-verb
  args schema to `contract.json`) **before** dropping the parser's order-arg coverage — otherwise
  `trail_percent` vs `trail_pct`-style drift passes the test and fails only at live order time.
  Adding `replace`/`close_all`/`close_position` verbs requires synchronized edits to
  `records.py` (`Literal` verb set), `schema.ts` `ALL_VERBS`, and `contract.json`.
- **NFR-4 — Daemon gate is the final safety.** Regardless of console-side validation, the daemon
  RiskManager/Broker remains authoritative and fail-closed.
- **NFR-5 — Property-based tests (Partial).** Hypothesis properties for pure functions: qty↔
  notional conversion, risk-budget clamp, protection-level resolution, price-sanity checks, and
  structured (de)serialization round-trips.

## 4. Affected Components (from code survey)

- `operator-console/src/mcp-server.ts` — register structured tools (replace single `steer`).
- `operator-console/src/steer-handler.ts` — build structured `SteeringCommand` from tool args
  (replaces parse-string flow); `parser.ts` deleted; `schema.ts` extended.
- `src/agent/steering/records.py` — `SteeringCommand` richer args (Alpaca params); contract.
- `src/agent/steering/commands.py` — replace `build_human_buy`/`_v_buy`/`_v_sell` with a
  structured order handler invoking RiskManager reception; new verbs for replace/close-all.
- `src/risk/manager.py` — reception/validation of a fully-specified Alpaca-shaped order
  (validate + clamp + auto-protect + price-sanity), structured reject result.
- `src/core/models.py` / `src/core/types.py` — `Order` extensions: trailing-stop fields,
  `notional`, `extended_hours`, OTO class, extended TIF.
- `src/execution/brokers/alpaca_broker.py` — map trailing-stop, notional, extended_hours,
  extended TIF, OTO; `replace_order`.

## 5. Out of Scope (deferred to later tracks)

Crypto orders (`place_crypto_order`), options orders/exercise (`place_option_order`, exercise/
DNE), account-config & watchlist mutations, and mirroring of read/market-data tools (reads keep
the existing `steer_read` / `market.py` path).

## 6. Open design points (resolved during Application Design, not now)

- `replace_order_by_id` semantics against resting bracket/OCO legs (gates `replace` shippability).
- Clamp interaction with bracket leg prices (clamping qty must keep legs consistent).
- Trailing-stop representation in the `Order` model and broker request.
- Whether OTO / extended TIF (opg/cls/ioc/fok) are fully wired now or **stubbed with explicit
  rejects** (default: explicit reject, never silent downgrade — FR-3).
- Exact override-flag surface for FR-5a (per-tool `force` arg vs separate confirm step) and which
  checks it may override (budget/pool/breaker) vs which are non-overridable (price-sanity,
  auto-protection).

## 7. Critic review log (2026-05-31)

Adversarial review (isolated-context `critic` subagent) cross-checked the assertions above against
real code. All 5 findings verified and folded in: FR-2 (hybrid, parser trimmed not deleted),
FR-3 (real model/broker build + TIF fail-closed), FR-5/FR-5a (human-path budget/pool/breaker is
net-new + operator override per user decision), FR-8 (replace/cancel_all/close_all net-new),
NFR-1 (defense-in-depth wording), NFR-3 (per-verb args contract before parser trim). Two policy
forks were put to the user: operator override authority (= limits apply, explicit override
allowed) and safety-verb determinism (= hybrid, safety verbs stay deterministic).
