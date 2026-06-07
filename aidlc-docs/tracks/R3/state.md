# Track R3 — Alpaca-shaped broker dedup (extract AlpacaShapedBroker base)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R3
- **Title**: Alpaca-shaped broker dedup — extract shared base from `alpaca_broker` + `broker_api_broker`
- **Type**: refactor
- **Status**: merge-awaiting  <!-- Build & Test green (1022 passed) + critic pass; committed on refactor/R3 -->
- **Branch**: refactor/R3
- **Worktree**: .claude/worktrees/R3
- **Submodule branch**: — (parent repo only; `src/execution/brokers/` is Python)
- **Base commit**: ec2875c
- **Start Date**: 2026-06-06

## Extension Configuration
- **Security Baseline**: Enabled — applicable: secrets handling stays unchanged (no new key surfaces;
  broker credentials already env-sourced). N/A: no new network endpoints, no auth changes.
- **Property-Based Testing**: Enabled (Hypothesis already used in `test_broker_api_broker.py`
  `TestMappersPBT`) — characterization PBT for the shared mappers (`_to_open_order`, `_to_fill_event`).

## Scope
Extract the ~80% duplicated logic between `src/execution/brokers/alpaca_broker.py` (602 LOC) and
`src/execution/brokers/broker_api_broker.py` (593 LOC) into a shared `AlpacaShapedBroker` base.
`broker_api_broker.py` self-documents as *"Mirror AlpacaBroker._build_request"*; both wrap the
alpaca-py SDK request/response shapes and differ only in the **client + request namespace**
(`alpaca.trading.requests` vs `alpaca.broker.requests`, `TradingClient` vs `BrokerClient`).

**Behavior-preserving (T1).** The two concrete brokers keep identical public behavior; only the
internal class hierarchy changes. See `inception/refactor/broker-dedup/2-tier-ledger.md`.

Related: [[risk-execution-redesign]] (bracket/OCO order shapes these brokers build),
[[kis-api-facts]] (KIS broker is the deliberately *separate* third broker — different SDK/semantics,
NOT folded into this base).

## Merge Risk Notes
> Filled when transitioning to `merge-awaiting`.
- **공유 파일 (주의)**: `src/execution/brokers/alpaca_broker.py`, `broker_api_broker.py`, new
  `src/execution/brokers/_alpaca_shaped.py`. `src/execution/base.py` only if a default moves up.
- **API/시그니처 변경**: none intended to public broker API (BaseBroker contract unchanged). Internal
  helper methods relocate to the base class — purely internal.
- **알려진 동시 변경**: F33 (multi-broker, paused) may touch broker wiring — coordinate before merge.

## Stage Progress (skill: ai-dlc-refactor)
- [x] Stage 1 — Baseline + characterization tests
  - [x] 1-baseline.md (current structure + preserved contract + coverage gap analysis)
  - [x] `tests/test_alpaca_broker.py` — 36 Alpaca-side characterization tests; green on baseline
- [x] Stage 2 — Tier ledger (`2-tier-ledger.md`); T3 gate resolved → **preserve all (fully T1)**;
      T3-1/T3-2 carved into R7
- [x] Stage 3 — Redesign (`3-redesign.md`) — `AlpacaShapedBroker` hook contract + equivalence + order
- [x] Stage 4 — Implementation (`4-implementation.md`) — base extracted; both subclasses green
- [x] Build & Test — full suite **1014 passed, 0 failed**; py_compile clean
      **(code committed? NO — awaiting user; see audit)**
