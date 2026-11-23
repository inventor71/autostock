"""Post-decision return evaluation. Future bars never enter a model sandbox.

Episodes start from identical frozen books and use the production executor.
They measure a single decision followed by its resting exits, not a continuous
strategy backtest. Synthetic paths validate accounting, never trading skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.agent.executor import DecisionExecutor
from src.agent.journal import Decision, Journal
from src.core.models import Position
from src.core.types import OrderSide, PositionSide
from src.evals.grading import FixturePriceProvider, replay_risk_manager
from src.evals.scenario import Scenario, load_scenario
from src.execution.brokers.simulated_broker import SimulatedBroker


class FutureBar(BaseModel):
    model_config = {"extra": "forbid"}
    open_at: datetime
    close_at: datetime
    open: float = Field(ge=0, allow_inf_nan=False)
    high: float = Field(ge=0, allow_inf_nan=False)
    low: float = Field(ge=0, allow_inf_nan=False)
    close: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_bar(self):
        if self.open_at.utcoffset() is None or self.close_at.utcoffset() is None:
            raise ValueError("Bar timestamps must include a timezone")
        if self.open_at >= self.close_at or not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Invalid OHLC range or bar interval")
        return self


class OutcomePath(BaseModel):
    model_config = {"extra": "forbid"}
    scenario_id: str
    as_of: datetime
    kind: Literal["synthetic", "historical", "forward"]
    provenance: str = Field(min_length=1)
    bars: dict[str, list[FutureBar]]
    benchmark: list[FutureBar]
    cost_bps_per_side: float = Field(default=10, ge=0, allow_inf_nan=False)
    borrow_apr: float = Field(default=0.03, ge=0, allow_inf_nan=False)
    cash_apr: float = Field(default=0, ge=0, allow_inf_nan=False)
    corporate_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def aligned_future(self):
        if self.as_of.utcoffset() is None or not self.benchmark or not self.bars:
            raise ValueError("A timezone-aware cutoff and complete future tape are required")
        grid = [(b.open_at, b.close_at) for b in self.benchmark]
        if grid[0][0] <= self.as_of or any(a[1] > b[0] for a, b in zip(grid, grid[1:])):
            raise ValueError("Future bars must follow the information cutoff without overlaps")
        if any([(b.open_at, b.close_at) for b in path] != grid for path in self.bars.values()):
            raise ValueError("Every symbol and benchmark must share the exact bar intervals")
        if self.corporate_actions:
            raise ValueError("Splits/dividends require a corporate-action-aware replay; this episode scorer cannot model them")
        return self


class _ReplayBroker(SimulatedBroker):
    """Charge friction on both sides and fill gapped stops at the adverse open."""
    def __init__(self, cash, cost):
        super().__init__(initial_capital=cash, commission_pct=cost)
        self.opens = {}
        self._range_pass = False
        self._intrabar_entries = set()
        self.intrabar_short_notional = 0.0

    def set_current_price(self, symbol, price, high=None, low=None):
        self._range_pass = high is not None or low is not None
        self._intrabar_entries = set()
        self.intrabar_short_notional = 0.0
        try:
            return super().set_current_price(symbol, price, high, low)
        finally:
            self._range_pass = False

    def _is_triggered(self, leg, high, low):
        if leg.role == "take_profit" and leg.symbol in self._intrabar_entries:
            # A target touch may have preceded a limit entry in the same bar.
            # Only its close is known to follow that entry; never award a gain
            # from an unobserved favorable ordering of the high and low.
            high = low = self._current_prices[leg.symbol]
        return super()._is_triggered(leg, high, low)

    def _fill_leg(self, leg, high, low):
        original = leg.trigger_price
        if leg.role == "stop_loss":
            opening = self.opens.get(leg.symbol, original)
            leg.trigger_price = (max(original, opening) if leg.side == OrderSide.BUY_TO_COVER
                                 else min(original, opening))
        try:
            fill = super()._fill_leg(leg, high, low)
            if fill is not None and leg.role == "entry" and self._range_pass:
                self._intrabar_entries.add(leg.symbol)
                if leg.side == OrderSide.SELL_SHORT:
                    self.intrabar_short_notional += fill.qty * fill.filled_price
            return fill
        finally:
            leg.trigger_price = original


def _book(scenario, path):
    account = scenario.tool_fixtures.get("account", {}).get("_", {})
    if "cash" not in account:
        raise ValueError("Return evaluation requires an explicit account cash snapshot")
    broker = _ReplayBroker(float(account["cash"]), path.cost_bps_per_side / 10000)
    for sym, price in scenario.prices.items():
        broker.set_current_price(sym, price)
    for sym, h in scenario.held.items():
        broker._positions[sym] = Position(
            symbol=sym, qty=h["qty"], avg_entry_price=h["avg_entry_price"],
            current_price=scenario.prices[sym],
            side=PositionSide.SHORT if h.get("side") == "short" else PositionSide.LONG,
        )
    # Existing protective orders belong to both the candidate and hold-book baseline.
    for sym, pos in broker._positions.items():
        orders = [o for o in account.get("open_orders", []) if o.get("symbol") == sym]
        if any(float(o.get("qty", pos.qty)) != pos.qty for o in orders):
            raise ValueError("Partial protective orders require a finer execution replay")
        if len([o for o in orders if o.get("stop_price")]) > 1 or len([o for o in orders if o.get("limit_price")]) > 1:
            raise ValueError("Multiple protective levels require a finer execution replay")
        stop = next((o["stop_price"] for o in orders if o.get("stop_price")), None)
        target = next((o["limit_price"] for o in orders if o.get("limit_price")), None)
        if stop is not None or target is not None:
            broker._arm_protection(sym, pos.qty, target, stop, short=pos.side == PositionSide.SHORT)
    return broker


def _simulate(scenario, path, decisions):
    broker = _book(scenario, path)
    initial = broker.get_portfolio_state().equity
    if initial <= 0 or not math.isfinite(initial):
        raise ValueError("Initial equity must be positive and finite")
    equity = [initial]
    gates = []
    entry_expiry = {}
    funding = 0.0
    previous = path.as_of
    def accrue(start, end):
        days = (end - start).total_seconds() / 86400
        short_value = sum(p.market_value for p in broker.get_all_positions()
                          if p.side == PositionSide.SHORT)
        borrow = short_value * path.borrow_apr * days / 365
        cash_yield = math.expm1(math.log1p(path.cash_apr) * days / 365)
        broker._cash += max(broker._cash - short_value, 0) * cash_yield - borrow
        return borrow
    with tempfile.TemporaryDirectory(prefix="autostock-returns-") as tmp:
        for index, reference_bar in enumerate(path.benchmark):
            opening = {sym: bars[index].open for sym, bars in path.bars.items()}
            broker.opens = opening
            funding += accrue(previous, reference_bar.open_at)
            for sym, price in opening.items():
                # Expired entry orders cannot fill at today's open.
                for leg in list(broker._resting.get(sym, [])):
                    expiry = entry_expiry.get(leg.leg_id)
                    if expiry and expiry < reference_bar.open_at:
                        broker.cancel_order(leg.leg_id)
                broker.set_current_price(sym, price)
            if index == 0:
                def clock(dt):
                    return (reference_bar.open_at.astimezone(dt.tzinfo) if dt.tzinfo
                            else reference_bar.open_at.replace(tzinfo=None))
                executor = DecisionExecutor(
                    broker, replay_risk_manager(scenario),
                    FixturePriceProvider(opening), Journal(tmp), universe=scenario.universe, clock=clock,
                )
                for decision in decisions:
                    outcome = executor.execute_decision(decision)
                    gates.append({"symbol": decision.symbol, "action": decision.action,
                                  "status": outcome.status, "detail": outcome.detail})
                    if decision.valid_until:
                        expiry = decision.valid_until
                        if expiry.utcoffset() is None:
                            raise ValueError("Return evaluation requires timezone-aware entry expiry")
                        for leg in broker._resting.get(decision.symbol, []):
                            if leg.role == "entry":
                                entry_expiry[leg.leg_id] = expiry
            # Charge the full bar's borrowing for positions open at its start;
            # an intrabar exit time is unknown at OHLC resolution.
            funding += accrue(reference_bar.open_at, reference_bar.close_at)
            for sym, bars in path.bars.items():
                bar = bars[index]
                # If expiry is within the bar, only the observed opening fill is
                # allowed. We cannot know whether a later touch preceded expiry.
                for leg in list(broker._resting.get(sym, [])):
                    expiry = entry_expiry.get(leg.leg_id)
                    if expiry and expiry < bar.close_at:
                        broker.cancel_order(leg.leg_id)
                broker.set_current_price(sym, bar.close, high=bar.high, low=bar.low)
                # An intrabar short entry was absent during the opening funding
                # charge. Conservatively charge it for the whole bar as well.
                borrow = (broker.intrabar_short_notional * path.borrow_apr
                          * (bar.close_at - bar.open_at).total_seconds() / (86400 * 365))
                broker._cash -= borrow
                funding += borrow
            equity.append(broker.get_portfolio_state().equity)
            previous = reference_bar.close_at
        # Value remaining positions at an executable exit, charging closing costs.
        for position in list(broker.get_all_positions()):
            broker.close_position(position.symbol)
        equity[-1] = broker.get_portfolio_state().equity
    fills = list(broker._fills.values())
    peak, drawdown = initial, 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    return {"net_return": equity[-1] / initial - 1, "max_drawdown": drawdown,
            "equity": equity, "turnover": sum(f.qty * f.filled_price for f in fills) / initial,
            "trading_cost": sum(f.commission for f in fills), "borrow_cost": funding,
            "fills": [f.model_dump(mode="json") for f in fills], "gates": gates}


def evaluate_returns(scenario: Scenario, path: OutcomePath, decisions: list[Decision]) -> dict:
    if scenario.id != path.scenario_id or scenario.as_of != path.as_of:
        raise ValueError("Scenario identity and information cutoff must match the hidden outcome")
    needed = set(scenario.universe) | set(scenario.held)
    if needed - path.bars.keys() or needed - scenario.prices.keys():
        raise ValueError("Missing cutoff prices or future bars; never drop losing/delisted symbols")
    result = _simulate(scenario, path, decisions)
    hold = _simulate(scenario, path, [])
    days = (path.benchmark[-1].close_at - path.as_of).total_seconds() / 86400
    friction = path.cost_bps_per_side / 10000
    if path.benchmark[0].open <= 0:
        raise ValueError("Benchmark needs a positive executable opening price")
    benchmark = path.benchmark[-1].close / path.benchmark[0].open * (1 - friction) / (1 + friction) - 1
    cash = math.expm1(math.log1p(path.cash_apr) * days / 365)
    return {**result, "kind": path.kind, "provenance": path.provenance,
            "cash_return": cash, "hold_book_return": hold["net_return"],
            "benchmark_return": benchmark,
            "excess_vs_hold": result["net_return"] - hold["net_return"],
            "excess_vs_benchmark": result["net_return"] - benchmark,
            "start": path.as_of.isoformat(), "end": path.benchmark[-1].close_at.isoformat()}


def paired_evidence(differences, *, intervals, kinds, seed=0, samples=2000, block_size=5):
    """Paired moving-block bootstrap, only for enough non-overlapping real episodes.

    Average repetitions for each case before calling this: repeated generations
    are not independent market outcomes. The interval is descriptive, not a
    multiple-comparison correction or a guarantee of future performance.
    """
    count = len(differences)
    result = {"episodes": count, "mean_difference": statistics.mean(differences) if count else None,
              "ci95": None, "status": "insufficient_evidence"}
    if not (len(intervals) == len(kinds) == count):
        raise ValueError("Paired evidence inputs must align")
    ordered = sorted(zip(intervals, differences), key=lambda item: item[0][0])
    if any(a[0][1] >= b[0][0] for a, b in zip(ordered, ordered[1:])):
        result["status"] = "overlapping_episodes"
        return result
    if "synthetic" in kinds:
        result["status"] = "synthetic_accounting_only"
        return result
    if count < max(20, 4 * block_size):
        return result
    values = [item[1] for item in ordered]
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        sample = []
        while len(sample) < count:
            start = rng.randrange(count)
            sample.extend(values[(start + i) % count] for i in range(block_size))
        means.append(statistics.mean(sample[:count]))
    means.sort()
    result.update(ci95=[means[int(samples * .025)], means[int(samples * .975)]],
                  status="historical_estimate" if "historical" in kinds else "forward_estimate")
    return result


def score_experiment(experiment: Path, outcomes_file: Path, baseline: str, baseline_mode="single"):
    manifest_path = experiment / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    payload = outcomes_file.read_bytes()
    outcomes = [OutcomePath.model_validate(p) for p in json.loads(payload)]
    if len({p.scenario_id for p in outcomes}) != len(outcomes):
        raise ValueError("Duplicate outcome paths")
    by_id = {p.scenario_id: p for p in outcomes}
    scenarios = {s.id: s for s in (load_scenario(p) for p in (experiment / "scenarios").glob("*.json"))}
    rows = []
    for file in sorted((experiment / "runs").glob("*.json")):
        run = json.loads(file.read_text())
        row = {k: run.get(k) for k in ("scenario_id", "profile", "mode", "repeat")}
        try:
            if (run.get("error") or run.get("metrics", {}).get("failed_calls", 0)
                    or not run.get("report") or not run["report"]["tier1"]["hard"]["extraction_ok"]):
                raise ValueError("Failed model/extraction run is unscored, not a cash decision")
            path = by_id[run["scenario_id"]]
            if path.kind == "forward":
                digest = hashlib.sha256(json.dumps(run["report"]["new_decisions"], sort_keys=True).encode()).hexdigest()
                finished = datetime.fromisoformat(run.get("finished_at", ""))
                if (finished.utcoffset() is None or finished >= path.benchmark[0].open_at
                        or finished < path.as_of or digest != run.get("decisions_sha256")):
                    raise ValueError("Forward evidence requires intact decisions recorded before future prices")
            row["score"] = evaluate_returns(scenarios[run["scenario_id"]], by_id[run["scenario_id"]],
                [Decision.model_validate(d) for d in run["report"]["new_decisions"]])
        except Exception as exc:
            row["error"] = str(exc)
        rows.append(row)
    baseline_rows = {(r["scenario_id"], r["repeat"]): r for r in rows
                     if r["profile"] == baseline and r["mode"] == baseline_mode}
    if not baseline_rows:
        raise ValueError("Requested baseline profile/mode is absent")
    summaries = []
    groups = {(r["profile"], r["mode"]) for r in rows}
    groups.update((p["name"], m) for p in manifest.get("profiles", []) for m in manifest.get("modes", []))
    for profile, mode in sorted(groups):
        selected = [r for r in rows if (r["profile"], r["mode"]) == (profile, mode)]
        paired = {}
        for row in selected:
            base = baseline_rows.get((row["scenario_id"], row["repeat"]))
            if "score" in row and base and "score" in base:
                paired.setdefault(row["scenario_id"], []).append(
                    row["score"]["net_return"] - base["score"]["net_return"])
        case_ids = sorted(paired)
        evidence = paired_evidence(
            [statistics.mean(paired[i]) for i in case_ids],
            intervals=[(by_id[i].as_of, by_id[i].benchmark[-1].close_at) for i in case_ids],
            kinds=[by_id[i].kind for i in case_ids],
        )
        planned = manifest.get("repeats", 1) * len(manifest.get("scenario_ids", [])) or len(selected)
        if sum(len(v) for v in paired.values()) != planned:
            evidence.update(ci95=None, status="incomplete_pairs")
        summaries.append({"profile": profile, "mode": mode, "runs": len(selected),
                          "planned_runs": planned,
                          "unscored": sum("score" not in r for r in selected) + max(planned-len(selected), 0), **evidence})
    report = {"outcome_sha256": hashlib.sha256(payload).hexdigest(), "baseline": baseline,
              "baseline_mode": baseline_mode, "summaries": summaries, "runs": rows,
              "limitations": ["Single-decision episodes, not a continuous portfolio backtest",
                              "Historical model-knowledge contamination remains possible",
                              "Daily bars cannot identify intrabar order; stops take precedence",
                              "No automatic promotion; multiple comparisons require a fresh holdout"]}
    root = Path(__file__).resolve().parents[2]
    replay_paths = ["src/evals/returns.py", "src/evals/grading.py", "src/agent/executor.py",
                    "src/execution/brokers/simulated_broker.py", "src/risk/manager.py",
                    "src/risk/position_sizer.py", "src/agent/aggressiveness.py", "main.py"]
    report["replay_source_sha256"] = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                                       for p in replay_paths}
    (experiment / "returns.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Return evaluation", "", *report["limitations"], "",
             "Differences are net of per-side trading friction and short borrowing costs.",
             "Failed/missing outcomes remain unscored; repetitions do not increase market sample size.", "",
             "| Profile | Mode | Episodes | Unscored runs | Mean paired difference | Evidence |",
             "| --- | --- | ---: | ---: | ---: | --- |"]
    for s in summaries:
        mean = f"{s['mean_difference']:.2%}" if s["mean_difference"] is not None else "unknown"
        lines.append(f"| {s['profile']} | {s['mode']} | {s['episodes']} | {s['unscored']} | {mean} | {s['status']} |")
    (experiment / "returns.md").write_text("\n".join(lines) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True, help="Hidden paths; never sent to models")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--baseline-mode", choices=("single", "sequential", "parallel"), default="single")
    args = parser.parse_args()
    report = score_experiment(args.experiment, args.outcomes, args.baseline, args.baseline_mode)
    print(json.dumps(report["summaries"], indent=2))


if __name__ == "__main__":
    main()
