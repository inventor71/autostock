"""Human-approval gate for agent decisions (BR-4, FR-8).

When the executor is about to run an agent-authored ``Decision`` on a symbol the
human has traded (``locked``) or twice-rejected (``denied``), this gate parks or
denies the *discretionary* (BUY/SELL) decision instead of executing it. Protective
actions (HOLD / ADJUST_STOP) are NEVER gated -- the "every position is protected"
invariant must not be blocked (BR-4.6). Lifecycle gating (paused / entries_halted)
is applied separately in the scheduler wiring, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.agent.journal import Decision
from src.agent.steering.records import PendingApproval
from src.agent.steering.state import SteeringState

# discretionary == directional bets the human can veto; protective is exempt.
DISCRETIONARY_ACTIONS = frozenset({"BUY", "SELL"})

GateAction = Literal["execute", "park", "deny"]


@dataclass
class GateResult:
    action: GateAction
    pending: PendingApproval | None = None
    detail: str = ""


def gate_agent_decision(decision: Decision, state: SteeringState) -> GateResult:
    """Decide whether an agent decision executes, parks for approval, or is denied."""
    # Protective / non-directional -> always execute (BR-4.6 exemption).
    if decision.action not in DISCRETIONARY_ACTIONS:
        return GateResult("execute")

    status = state.lock_status(decision.symbol)
    if status is None:
        return GateResult("execute")
    if status == "denied":
        # BR-4.5: auto-reject, no PendingApproval; caller feeds the agent back.
        return GateResult("deny", detail=f"{decision.symbol} human-denied for the day")
    # locked -> park for approval (idempotent on fingerprint; may return None if
    # an identical decision is already parked, in which case treat as parked).
    pending = state.add_pending(decision)
    return GateResult("park", pending=pending,
                      detail=f"{decision.symbol} human-locked; parked for approval")
