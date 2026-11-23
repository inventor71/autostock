"""Return accounting and evidence strength, independent of model profitability."""

from datetime import datetime, timedelta, timezone

import pytest

from src.agent.journal import Decision
from src.evals.returns import FutureBar, OutcomePath, evaluate_returns, paired_evidence
from src.evals.scenario import Expectation, Scenario

START = datetime(2026, 1, 5, 21, tzinfo=timezone.utc)


def bar(day, opening, high, low, close):
    return FutureBar(open_at=START + timedelta(days=day, hours=-6),
                     close_at=START + timedelta(days=day),
                     open=opening, high=high, low=low, close=close)


def case(bars=None, cost=10, **kwargs):
    scenario = Scenario(id="return-case", turn_type="research", as_of=START,
        universe=["X"], prices={"X":100}, expectation=Expectation(no_churn=True),
        tool_fixtures={"account":{"_":{"cash":100000, "equity":100000}}})
    bars = bars or [bar(1,100,102,99,101), bar(2,101,103,100,102)]
    path = OutcomePath(scenario_id=scenario.id, as_of=START, kind="synthetic",
        provenance="Deterministic accounting fixture, never investment evidence",
        bars={"X":bars}, benchmark=[b.model_copy(update={"open":100,"high":100,"low":100,"close":100}) for b in bars],
        cost_bps_per_side=cost, **kwargs)
    return scenario, path


def buy(**kwargs):
    return Decision(symbol="X", action="BUY", stop=95, target=120, confidence=1, **kwargs)


def test_real_risk_sizing_and_roundtrip_friction():
    scenario, path = case()
    result = evaluate_returns(scenario, path, [buy()])
    entry, exit = result["fills"]
    qty = entry["qty"]
    expected = qty * (102-100) - qty * (100+102) * .001
    assert result["net_return"] == pytest.approx(expected / 100000)
    assert result["trading_cost"] == pytest.approx(qty * .202)
    assert result["hold_book_return"] == 0
    assert result["turnover"] == pytest.approx(qty * 202 / 100000)


def test_small_gross_gain_loses_after_costs_so_no_trade_can_win():
    scenario, path = case([bar(1,100,100.05,99.99,100.05)], cost=10)
    active = evaluate_returns(scenario, path, [buy()])
    wait = evaluate_returns(scenario, path, [])
    assert active["net_return"] < 0
    assert wait["net_return"] == 0
    assert active["excess_vs_hold"] < 0


def test_stop_gap_uses_worse_open_and_never_optimistic_stop_price():
    scenario, path = case([bar(1,100,101,99,100),bar(2,80,90,75,85)], cost=0)
    result = evaluate_returns(scenario, path, [buy()])
    assert result["fills"][1]["filled_price"] == 80
    qty = result["fills"][0]["qty"]
    assert result["net_return"] == pytest.approx(-20 * qty / 100000)
    assert result["max_drawdown"] == pytest.approx(result["net_return"])


def test_same_bar_stop_and_target_assumes_stop_first():
    scenario, path = case([bar(1,100,125,90,110)], cost=0)
    result = evaluate_returns(scenario, path, [buy()])
    assert result["fills"][1]["filled_price"] == 95
    assert result["net_return"] < 0


def test_market_entry_occurs_at_next_open_not_cutoff_close():
    scenario, path = case([bar(1,110,111,109,110)], cost=0)
    result = evaluate_returns(scenario, path, [Decision(symbol="X",action="BUY",stop=105,target=125,confidence=.8)])
    assert result["fills"][0]["filled_price"] == 110
    assert result["net_return"] == 0


def test_unfilled_limit_and_expiry_cannot_invent_a_trade():
    scenario, path = case([bar(1,100,102,99,101)], cost=0)
    result = evaluate_returns(scenario, path, [buy(limit=98)])
    assert not result["fills"] and result["net_return"] == 0
    expired = evaluate_returns(scenario, path, [buy(valid_until=START + timedelta(hours=1))])
    assert not expired["fills"] and expired["gates"][0]["status"] == "skipped_expired"


def test_short_return_has_correct_direction_and_borrow_cost():
    scenario, path = case([bar(1,100,101,89,90)], cost=0, borrow_apr=.365)
    scenario.shorting_enabled = True
    result = evaluate_returns(scenario, path, [Decision(symbol="X",action="SELL_SHORT",stop=105,target=80,confidence=1)])
    qty = result["fills"][0]["qty"]
    assert result["borrow_cost"] > 0
    assert result["net_return"] == pytest.approx((qty * 10 - result["borrow_cost"]) / 100000)


@pytest.mark.parametrize("short", [False, True])
def test_intrabar_entry_cannot_profit_from_a_target_touched_before_entry(short):
    tape = [bar(1,100,103,89,101)] if short else [bar(1,100,111,97,99)]
    scenario, path = case(tape, cost=0)
    scenario.shorting_enabled = short
    decision = (Decision(symbol="X",action="SELL_SHORT",limit=102,stop=106,target=90,confidence=1)
                if short else Decision(symbol="X",action="BUY",limit=98,stop=95,target=110,confidence=1))
    result = evaluate_returns(scenario,path,[decision])
    entry, exit = result["fills"]
    assert entry["filled_price"] == (102 if short else 98)
    assert exit["filled_price"] == (101 if short else 99)  # conservative terminal close, not target
    if short:
        assert result["borrow_cost"] > 0  # a late entry still incurs funding


def test_adjacent_bar_intervals_are_valid():
    scenario,path=case()
    payload=path.model_dump()
    for tape in [payload["benchmark"],*payload["bars"].values()]:
        tape[1]["open_at"] = tape[0]["close_at"]
    assert evaluate_returns(scenario,OutcomePath.model_validate(payload),[])["net_return"] == 0


def test_hidden_paths_reject_lookahead_misalignment_and_missing_losers():
    scenario, path = case()
    with pytest.raises(ValueError, match="cutoff"):
        OutcomePath.model_validate({**path.model_dump(), "as_of": path.benchmark[0].open_at})
    with pytest.raises(ValueError, match="exact bar"):
        OutcomePath.model_validate({**path.model_dump(), "bars":{"X":path.bars["X"][:1]}})
    scenario.universe.append("DELISTED")
    with pytest.raises(ValueError, match="Missing"):
        evaluate_returns(scenario,path,[])


def test_total_loss_is_recordable_instead_of_dropping_delisted_symbol():
    scenario, path = case([bar(1,100,101,99,100),bar(2,0,0,0,0)], cost=0)
    result = evaluate_returns(scenario,path,[buy()])
    assert result["fills"][1]["filled_price"] == 0
    assert result["net_return"] < 0


def intervals(n):
    return [(START+timedelta(days=3*i), START+timedelta(days=3*i+1)) for i in range(n)]


def test_tiny_synthetic_or_overlapping_samples_cannot_establish_better_returns():
    assert paired_evidence([.1]*6, intervals=intervals(6), kinds=["historical"]*6)["ci95"] is None
    synthetic = paired_evidence([.1]*30, intervals=intervals(30), kinds=["synthetic"]*30)
    assert synthetic["ci95"] is None and synthetic["status"] == "synthetic_accounting_only"
    overlap = paired_evidence([.1]*30, intervals=[intervals(1)[0]]*30,kinds=["forward"]*30)
    assert overlap["ci95"] is None and overlap["status"] == "overlapping_episodes"


def test_paired_intervals_are_reproducible_and_can_show_no_advantage():
    args=dict(intervals=intervals(40),kinds=["historical"]*40,seed=17)
    result=paired_evidence([.01,-.01]*20,**args)
    assert result == paired_evidence([.01,-.01]*20,**args)
    assert result["ci95"][0] < 0 < result["ci95"][1]


def test_scoring_collapses_repeats_and_retains_failed_runs(tmp_path):
    import json
    from src.evals.scenario import save_scenario
    from src.evals.returns import score_experiment

    scenario, path = case()
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "runs").mkdir()
    save_scenario(scenario,tmp_path / "scenarios/case.json")
    outcomes = tmp_path / "outcomes.json"
    outcomes.write_text(json.dumps([path.model_dump(mode="json")]))
    for repeat in range(25):
        for profile in ("baseline","candidate"):
            row = {"scenario_id":scenario.id,"profile":profile,"mode":"single","repeat":repeat,
                   "report":{"new_decisions": [], "tier1":{"hard":{"extraction_ok":True}}}}
            if profile == "candidate" and repeat == 24:
                row["error"] = "model timeout"
            (tmp_path / "runs" / f"{repeat}-{profile}.json").write_text(json.dumps(row))
    report = score_experiment(tmp_path,outcomes,"baseline")
    candidate = next(s for s in report["summaries"] if s["profile"] == "candidate")
    assert candidate["episodes"] == 1 and candidate["unscored"] == 1
    assert candidate["ci95"] is None and candidate["status"] == "incomplete_pairs"
    assert report["replay_source_sha256"] and (tmp_path / "returns.md").exists()


def test_forward_scoring_requires_decisions_sealed_before_prices(tmp_path):
    import hashlib,json
    from src.evals.scenario import save_scenario
    from src.evals.returns import score_experiment

    scenario,path=case()
    path.kind="forward"
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "runs").mkdir()
    save_scenario(scenario,tmp_path / "scenarios/case.json")
    outcomes=tmp_path / "outcomes.json"
    outcomes.write_text(json.dumps([path.model_dump(mode="json")]))
    row={"scenario_id":scenario.id,"profile":"baseline","mode":"single","repeat":0,
         "report":{"new_decisions":[],"tier1":{"hard":{"extraction_ok":True}}},
         "finished_at":(START+timedelta(minutes=1)).isoformat(),
         "decisions_sha256":hashlib.sha256(b'[]').hexdigest()}
    file=tmp_path / "runs/run.json"
    file.write_text(json.dumps(row))
    assert "score" in score_experiment(tmp_path,outcomes,"baseline")["runs"][0]
    row["finished_at"] = path.benchmark[-1].close_at.isoformat()
    file.write_text(json.dumps(row))
    assert "before future prices" in score_experiment(tmp_path,outcomes,"baseline")["runs"][0]["error"]
