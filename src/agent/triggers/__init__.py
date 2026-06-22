"""F88 — agent self-authored long-horizon triggers.

The agent registers a long-horizon trigger (a Python ``should_fire(ctx)`` predicate
plus a declared set of data sources) via the daemon's MCP server. The daemon
evaluates it on a slow cadence (hourly floor): it brokers the declared data into a
``ctx`` snapshot (the predicate itself has NO network), runs the predicate in a
one-shot Docker sandbox (autostock ``src/`` un-mounted, ``--network=none``, secrets
stripped), and on ``fire=True`` schedules a ``WakeEvent(kind="agent_trigger")`` —
the agent's existing supervisor gate still governs any resulting trade.

Two planes (see ``aidlc-docs/tracks/F88``):
  * control plane (trusted): ``TriggerStore``, ``AstScreen``, ``BrokeredFetcher``,
    ``TriggerEvaluator``, ``TriggerMcpServer``.
  * execution plane (untrusted): the predicate, run only inside ``SandboxRunner``.

U1 ships the foundation: data models, the store, and the static pre-screen.
"""

from __future__ import annotations

from src.agent.triggers.ast_screen import AstScreen, AstViolation
from src.agent.triggers.evaluator import TriggerEvaluator
from src.agent.triggers.fetch import BrokeredFetcher, default_http_get
from src.agent.triggers.models import (
    SIGNAL_NAMES,
    SourceRef,
    TriggerDetail,
    TriggerSpec,
    TriggerState,
    TriggerSummary,
    Verdict,
)
from src.agent.triggers.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxRunner,
)
from src.agent.triggers.store import TriggerStore

__all__ = [
    "AstScreen",
    "AstViolation",
    "BrokeredFetcher",
    "default_http_get",
    "SIGNAL_NAMES",
    "SandboxConfig",
    "SandboxResult",
    "SandboxRunner",
    "SourceRef",
    "TriggerDetail",
    "TriggerSpec",
    "TriggerEvaluator",
    "TriggerState",
    "TriggerStore",
    "TriggerSummary",
    "Verdict",
]
