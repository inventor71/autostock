"""Tier-1 deterministic grading.

Three layers, separated by how trustworthy a FAIL is:
- ``hard``: schema/extraction integrity — deterministic, CI-gateable.
- ``behavior``: did the agent act/no-churn as the scenario expects — the
  *input* is an LLM turn, so these are reported as signals, never hard gates
  (user decision, NFR-3).
- ``executor``: each emitted decision replayed through the REAL
  ``DecisionExecutor`` (SimulatedBroker + bracket-mode RiskManager) so
  guardrail verdicts come from production code, not a re-implementation
  (FR-5; rule drift impossible by construction).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.models import Position
from src.core.types import PositionSide

from src.evals.artifacts import TurnArtifacts
from src.evals.scenario import Expectation, Scenario


class FixturePriceProvider:
    """Prices for the executor replay come from the scenario, nowhere else."""

    def __init__(self, prices: dict[str, float]):
        self._prices = {k.upper(): float(v) for k, v in prices.items()}

    def get_latest_price(self, symbol: str) -> float:
        sym = symbol.upper()
        if sym not in self._prices:  # fail-honest: no silent live fetch
            raise LookupError(f"scenario defines no replay price for {sym}")
        return self._prices[sym]

    def get_bars(self, symbol: str, limit: int = 0):
        raise NotImplementedError(
            "executor replay has no bar history; scenarios must carry explicit "
            "stops so the ATR fallback path is never needed"
        )


def _seeded_broker(scenario: Scenario):
    from src.execution.brokers.simulated_broker import SimulatedBroker

    broker = SimulatedBroker()
    # Every replay symbol needs a simulated tape price BEFORE any order lands,
    # held or not — a fresh BUY fills at this price.
    for sym, price in scenario.prices.items():
        broker.set_current_price(sym.upper(), float(price))
    for sym, h in scenario.held.items():
        sym = sym.upper()
        price = scenario.prices.get(sym, float(h["avg_entry_price"]))
        # Seeding the book directly: SimulatedBroker has no deposit/transfer
        # API, and routing a fake entry order through it would consume cash and
        # emit fills the scenario never described.
        broker._positions[sym] = Position(
            symbol=sym,
            qty=float(h["qty"]),
            side=PositionSide.SHORT if h.get("side") == "short" else PositionSide.LONG,
            avg_entry_price=float(h["avg_entry_price"]),
            current_price=price,
        )
        broker.set_current_price(sym, price)
    return broker


def replay_through_executor(
    scenario: Scenario, decisions, *, journal_root: str | Path
) -> list[dict[str, Any]]:
    """Run each new decision through the real executor gate; collect statuses.

    ``journal_root`` MUST be the sandbox workspace — DecisionExecutor defaults
    its journal to the live workspace and logs executions there."""
    from src.agent.executor import DecisionExecutor
    from src.agent.journal import Journal
    from src.risk.manager import RiskManager

    executor = DecisionExecutor(
        broker=_seeded_broker(scenario),
        risk_manager=RiskManager(use_bracket_orders=True),
        data_provider=FixturePriceProvider(scenario.prices),
        journal=Journal(journal_root),
        universe=scenario.universe,
    )
    results = []
    for d in decisions:
        try:
            outcome = executor.execute_decision(d)
            results.append({
                "symbol": d.symbol, "action": d.action,
                "status": outcome.status, "detail": outcome.detail,
            })
        except Exception as exc:
            results.append({
                "symbol": d.symbol, "action": d.action,
                "status": "replay_error", "detail": str(exc),
            })
    return results


def behavior_grade(decisions, expectation: Expectation) -> dict[str, Any]:
    relevant = [
        d for d in decisions
        if expectation.focus_symbol is None or d.symbol == expectation.focus_symbol
    ]
    if expectation.no_churn:
        # Doing nothing — or merely re-affirming protection via HOLD — is the
        # correct behavior; anything else is churn.
        ok = all(d.action == "HOLD" for d in relevant)
    else:
        ok = any(d.action in expectation.allowed_actions for d in relevant)
    cited = sum(1 for d in decisions if d.lessons_cited)
    return {
        "matched": ok,
        "relevant_actions": [(d.symbol, d.action) for d in relevant],
        "lessons_cited_rate": (cited / len(decisions)) if decisions else None,
    }


def grade_tier1(
    scenario: Scenario, artifacts: TurnArtifacts, *, journal_root: str | Path
) -> dict[str, Any]:
    replay = replay_through_executor(
        scenario, artifacts.new_decisions, journal_root=journal_root)
    return {
        "hard": {
            "extraction_ok": artifacts.extraction_ok,
            "raw_line_delta": artifacts.raw_line_delta,
            "parsed_delta": artifacts.parsed_delta,
        },
        "behavior": behavior_grade(artifacts.new_decisions, scenario.expectation),
        "executor_replay": replay,
    }
