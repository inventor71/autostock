"""Behavioral regressions for the frontier-model prompt/feedback update."""

import json
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from src.agent.journal import Decision, Journal, LessonRecord
from src.agent.learning.efficacy import applied_counts, lesson_efficacy
from src.agent.learning.review import outcome_lines
from src.agent.orchestrator import AgentTradingLoop
from src.agent.quality.metrics import (
    benchmark_excess, confidence_calibration, direction_hit_rate, mae, mfe,
    realized_rr, stop_quality, target_quality,
)
from src.agent.quality.models import DecisionOutcome, OHLC, RoundTrip
from src.agent.quality.snapshot import quality_snapshot
from src.agent.session import AgentSession, AgentTurnResult
from src.risk.position_sizer import PositionSizer
from src.strategy.llm.prompt_manager import PromptManager
from src.strategy.llm.auto_improver import PromptAutoImprover
from src.strategy.llm.strategy import LLMStrategy


def _bar(day, close, low=None, high=None):
    return OHLC(date=day, open=close, high=high or close, low=low or close, close=close)


def test_benchmark_uses_each_decisions_exact_dates_and_short_direction():
    path = [_bar("2026-01-06", 100), _bar("2026-01-07", 110)]
    benchmark = [
        {"date": "2026-01-05", "close": 50},  # unrelated prior rally
        {"date": "2026-01-06 00:00:00", "close": 100},
        {"date": "2026-01-07", "close": 102},
        {"date": "2026-01-08", "close": 200},  # unrelated later rally
    ]
    for action, expected in (("BUY", 0.08), ("SELL_SHORT", -0.12)):
        outcome = DecisionOutcome(decision=Decision(symbol="X", action=action), price_path=path)
        result = benchmark_excess(outcome, benchmark, None)
        assert result["vs_spy"] == pytest.approx(expected)
        assert result["vs_qqq"] is None
        assert benchmark_excess(outcome, benchmark[:2], None)["vs_spy"] is None


def test_short_metrics_reward_falling_price_and_do_not_invent_stop_hit():
    outcome = DecisionOutcome(
        decision=Decision(symbol="X", action="SELL_SHORT", stop=105, target=90, confidence=0.8),
        price_path=[_bar("2026-01-05", 100, 99, 102), _bar("2026-01-06", 90, 88, 101)],
        round_trip=RoundTrip(symbol="X", qty=10, entry_price=100, exit_price=90,
                             opened_at="2026-01-05", closed_at="2026-01-06",
                             realized_pnl=100, return_pct=10),
    )
    assert direction_hit_rate([outcome])["hits"] == 1
    assert confidence_calibration([outcome])["0.7-0.9"]["hits"] == 1
    assert mae(outcome) == pytest.approx(0.02)
    assert mfe(outcome) == pytest.approx(0.12)
    assert realized_rr(outcome) == pytest.approx(2.0)
    assert stop_quality(outcome) == "n/a"
    assert target_quality(outcome)["reached"] is True


def test_unmatured_results_do_not_become_review_evidence():
    outcome = DecisionOutcome(
        decision=Decision(symbol="X", action="BUY", confidence=0.9), mature=False,
        price_path=[_bar("2026-01-05", 100), _bar("2026-01-06", 120)],
    )
    assert direction_hit_rate([outcome])["total"] == 0
    assert sum(b["count"] for b in confidence_calibration([outcome]).values()) == 0
    assert quality_snapshot([outcome] * 10) is None


def test_repeated_lesson_id_cannot_inflate_learning_sample():
    decision = Decision(symbol="X", action="BUY", lessons_cited=["L1"] * 30)
    outcome = DecisionOutcome(decision=decision, excess=0.1)
    assert applied_counts([decision]) == {"L1": 1}
    assert lesson_efficacy([outcome])["L1"].applied_n == 1


@pytest.mark.parametrize("excess", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_outcomes_do_not_become_learning_evidence(excess):
    decision = Decision(symbol="X", action="BUY", lessons_cited=["L1"])
    measured = lesson_efficacy([DecisionOutcome(decision=decision, excess=excess)])["L1"]
    assert measured.applied_n == 0
    assert measured.avg_excess is None


@pytest.mark.parametrize("price", [float("inf"), float("nan"), -1, None, True, "invalid"])
def test_missing_or_invalid_price_is_not_recorded_as_an_entry_anchor(tmp_path, price):
    session = AgentSession(workspace=tmp_path)
    loop = AgentTradingLoop(session=session, universe=["X"], price_provider=lambda sym: price)
    decision = Decision(symbol="X", action="BUY")
    loop._stamp_ref_prices([decision])
    assert decision.ref_price is None


@pytest.mark.parametrize("response", [
    "Do not BUY.", "Do not SELL.", 'Do not execute this example: {"signal":"BUY"}',
    '{"signal":"BUY"}\n{"signal":"HOLD"}', '[{"signal":"BUY"}]',
    '{"signal":"BUY","confidence":NaN}', '{"signal":"BUY","confidence":1e999}',
    '{"signal":"BUY","confidence":"NaN"}', '{"signal":"BUY","confidence":true}',
    '{"signal":"SELL","sell_pct":"half"}', '{"signal":"SELL","sell_pct":1.5}',
])
def test_ambiguous_or_nonfinite_model_output_cannot_trade(response):
    result = LLMStrategy()._parse_llm_response(response)
    assert result["signal"] == "HOLD"
    assert result["confidence"] == 0


def test_single_fenced_decision_remains_supported():
    parsed = LLMStrategy()._parse_llm_response(
        '```json\n{"signal":"BUY","confidence":0.7,"key_levels":{"stop_loss":95}}\n```'
    )
    assert parsed["signal"] == "BUY"
    assert parsed["key_levels"]["stop_loss"] == 95


def test_null_optional_fractions_keep_existing_strategy_compatibility():
    parsed = LLMStrategy()._parse_llm_response(
        '{"signal":"BUY","confidence":null,"sell_pct":null}'
    )
    assert parsed["signal"] == "BUY"
    assert parsed["confidence"] is None


def test_single_pass_gets_selected_lessons_and_current_short_permission(tmp_path, monkeypatch):
    session = AgentSession(workspace=tmp_path)
    observed = []
    def run(prompt, **kwargs):
        observed.append(prompt)
        return AgentTurnResult("No action", "test", False)
    monkeypatch.setattr(session, "run_turn", run)
    loop = AgentTradingLoop(session=session, universe=["X"], shorting_enabled=False)
    monkeypatch.setattr(loop, "_get_lessons", lambda: [
        LessonRecord(lesson_id="L42", takeaway="Check independent evidence")])
    loop.run_morning_research()
    assert "L42" in observed[0]
    assert "New short entries are disabled" in observed[0]
    assert observed[0].count("## Decision standard") == 1


def test_short_review_reports_return_on_entry_and_correct_stop_side():
    broker = SimpleNamespace(get_position=lambda _: SimpleNamespace(
        qty=10, avg_entry_price=100, side=SimpleNamespace(value="short")))
    provider = SimpleNamespace(get_latest_price=lambda _: 90)
    d = Decision(symbol="X", action="SELL_SHORT", stop=105, target=90)
    line = outcome_lines([d], broker, provider)[0]
    assert "+10.0%" in line and "at/below target" in line
    provider.get_latest_price = lambda _: 106
    assert "at/above stop" in outcome_lines([d], broker, provider)[0]


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -0.1, 1.5])
def test_position_sizing_cannot_expand_caps_with_invalid_confidence(confidence):
    portfolio = SimpleNamespace(equity=100000, cash=100000)
    assert PositionSizer().calculate_shares("X", 100, portfolio, confidence=confidence) == 0


def test_empty_prompt_history_loads_new_version_without_losing_original(tmp_path):
    (tmp_path / "prompt_history.json").write_text('{"versions":{},"current_version":"v1"}')
    (tmp_path / "trading_prompt_v1.txt").write_text("original")
    (tmp_path / "trading_prompt_v2.txt").write_text("current")
    manager = PromptManager(tmp_path)
    assert manager.get_prompt("latest").version == "v2"
    assert manager.get_prompt("v1").content == "original"
    manager.save_prompt("custom", version="v3")
    assert PromptManager(tmp_path).get_prompt("latest").content == "custom"


def test_signal_records_actual_prompt_version_instead_of_latest_alias(tmp_path):
    manager = PromptManager(tmp_path)
    manager.save_prompt("Use supplied evidence", version="v7")
    strategy = LLMStrategy({"include_news": False})
    strategy._prompt_manager = manager
    strategy._client = SimpleNamespace(model="test", complete=lambda **kw:
                                      '{"signal":"HOLD","confidence":0.5}')
    strategy._formatter = SimpleNamespace(format_for_llm=lambda *args: "Frozen evidence")
    result = strategy.generate_signal("X", pd.DataFrame())
    assert result.metadata["prompt_version"] == "v7"


def test_unchanged_improvement_does_not_create_or_activate_new_prompt(tmp_path, monkeypatch):
    manager = PromptManager(tmp_path)
    manager.save_prompt("Current guidance", version="v1")
    client = SimpleNamespace(complete=lambda **kw: json.dumps({
        "improved_prompt": "  Current guidance\n", "analysis": {}, "improvements": [],
    }))
    improver = PromptAutoImprover(llm_client=client, prompt_manager=manager)
    monkeypatch.setattr(improver, "_format_analysis_context", lambda *args: "Sparse evidence")
    assert improver.analyze_and_improve("v1", [object()]) is None
    assert list(manager.history.versions) == ["v1"]
    assert manager.history.current_version == "v1"


def test_collector_handles_real_fill_round_trip_and_aligned_benchmark(tmp_path, monkeypatch):
    from src.agent.quality.collector import collect_outcomes

    journal = Journal(tmp_path)
    journal.init()
    journal.append_decision(Decision(
        ts=datetime(2026, 1, 5, 14, 30), symbol="X", action="BUY", stop=95,
    ))
    (tmp_path / "execution_log.jsonl").write_text(json.dumps({
        "decision_index": 0, "symbol": "X", "action": "BUY", "order_id": "entry",
        "filled_qty": 10, "filled_price": 100, "ts": "2026-01-05T14:30:00",
    }) + "\n")
    index = pd.to_datetime(["2026-01-05", "2026-01-06"])
    def prices(closes):
        return pd.DataFrame({k: closes for k in ("Open", "High", "Low", "Close")}, index=index)
    cache = {"X": prices([100, 110]), "SPY": prices([100, 102]), "QQQ": prices([100, 102])}
    monkeypatch.setattr("src.agent.quality.collector._fetch_daily_ohlc", lambda *a, **kw: cache)
    fills = [
        {"symbol": "X", "side": "buy", "qty": 10, "price": 100, "ts": "2026-01-05T14:30:00"},
        {"symbol": "X", "side": "sell", "qty": 10, "price": 110, "ts": "2026-01-06T14:30:00"},
    ]
    outcome, = collect_outcomes(journal, fills=fills)
    assert outcome.round_trip.realized_pnl == 100
    assert outcome.mature is True
    assert outcome.excess == pytest.approx(0.08)
    assert realized_rr(outcome) == pytest.approx(2.0)
