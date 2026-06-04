"""F54 — Unit B (Agent Intelligence) tests: short analysis tools, account
direction-awareness, prompt/steering wiring."""

from __future__ import annotations

from src.agent.tools import market
from src.agent import prompts
from src.agent.steering.records import PlaceOrderArgs
from src.core.models import PortfolioState, Position
from src.core.types import PositionSide


class _FakeTicker:
    def __init__(self, info: dict):
        self._info = info

    def __call__(self, symbol: str):
        return self

    @property
    def info(self):
        return self._info


class TestShortDataTool:
    def test_high_squeeze_flag(self):
        tf = _FakeTicker({"shortPercentOfFloat": 0.45, "shortRatio": 6.0,
                          "sharesShort": 10_000_000, "sharesShortPriorMonth": 8_000_000})
        out = market.short_data("X", ticker_factory=tf)
        assert out["squeeze_risk"] == "HIGH"
        assert out["short_percent_of_float"] == 45.0
        assert out["short_interest_change_pct"] == 25.0
        assert "broker-determined" in out["borrow_availability"]

    def test_elevated_squeeze_flag(self):
        tf = _FakeTicker({"shortPercentOfFloat": 0.25})
        assert market.short_data("X", ticker_factory=tf)["squeeze_risk"] == "ELEVATED"

    def test_low_squeeze_flag(self):
        tf = _FakeTicker({"shortPercentOfFloat": 0.05})
        assert market.short_data("X", ticker_factory=tf)["squeeze_risk"] == "LOW"

    def test_unknown_when_missing(self):
        tf = _FakeTicker({})
        out = market.short_data("X", ticker_factory=tf)
        assert out["squeeze_risk"] == "UNKNOWN"
        assert out["short_percent_of_float"] is None

    def test_error_tolerant(self):
        def boom(symbol):
            raise RuntimeError("network")
        out = market.short_data("X", ticker_factory=boom)
        assert "error" in out


class _StubBroker:
    def __init__(self, positions):
        self._pf = PortfolioState(cash=50_000, equity=50_000, positions=positions)

    def get_portfolio_state(self):
        return self._pf

    def get_open_orders(self):
        return []


class TestAccountToolDirection:
    def test_short_unrealized_pct_sign(self):
        short = Position(symbol="X", qty=10, avg_entry_price=100, side=PositionSide.SHORT)
        short.update_price(90)  # short up 10%
        out = market.account(_StubBroker({"X": short}))
        pos = out["positions"][0]
        assert pos["side"] == "short"
        assert pos["unrealized_pct"] > 0  # profit shown positive
        assert pos["unrealized_pnl"] > 0

    def test_long_unrealized_pct_unchanged(self):
        long = Position(symbol="Y", qty=10, avg_entry_price=100)  # LONG default
        long.update_price(110)
        out = market.account(_StubBroker({"Y": long}))
        pos = out["positions"][0]
        assert pos["side"] == "long"
        assert pos["unrealized_pct"] > 0


class TestPromptShortWiring:
    def test_verdict_schema_lists_short_actions(self):
        assert "SELL_SHORT" in prompts._VERDICT_SCHEMA
        assert "BUY_TO_COVER" in prompts._VERDICT_SCHEMA

    def test_signal_guide_has_short_data(self):
        assert "short_data" in prompts._SIGNAL_TOOL_GUIDE

    def test_morning_prompt_includes_short_guidance(self):
        p = prompts.morning_research_prompt(["AAPL"], ["AAPL"])
        assert "SELL_SHORT" in p and "squeeze" in p.lower()

    def test_multi_research_includes_short_guidance(self):
        p = prompts.multi_research_initial_prompt(["AAPL"], ["AAPL"])
        assert "short" in p.lower()


class TestReviewShortPnL:
    """critic #2: the agent's EOD review must report a short's P&L with the right
    sign + a SHORT label, not the long-only formula."""

    def _outcome_line(self, side: PositionSide, entry: float, price: float):
        from datetime import datetime
        from src.agent import review
        from src.agent.journal import Decision

        class _Broker:
            def get_position(self, sym):
                p = Position(symbol=sym, qty=10, avg_entry_price=entry, side=side)
                p.update_price(price)
                return p

        class _DP:
            def get_latest_price(self, sym):
                return price

        d = Decision(symbol="X", action="SELL_SHORT" if side == PositionSide.SHORT else "BUY",
                     ts=datetime.now())
        return review.outcome_lines([d], _Broker(), _DP())[0]

    def test_winning_short_shows_positive_pct_and_label(self):
        line = self._outcome_line(PositionSide.SHORT, entry=100, price=90)
        assert "SHORT" in line
        assert "+" in line.split("held")[1]  # positive pct on the holding segment

    def test_losing_short_shows_negative_pct(self):
        line = self._outcome_line(PositionSide.SHORT, entry=100, price=110)
        assert "SHORT" in line and "-" in line.split("held")[1]

    def test_long_review_unchanged(self):
        line = self._outcome_line(PositionSide.LONG, entry=100, price=120)
        assert "SHORT" not in line and "+" in line.split("held")[1]


class TestPlaceOrderArgsShort:
    def test_sell_short_side_accepted(self):
        a = PlaceOrderArgs(symbol="X", side="sell_short", qty=10,
                           stop_loss=110, take_profit=85)
        assert a.side == "sell_short"

    def test_buy_to_cover_side_accepted(self):
        a = PlaceOrderArgs(symbol="X", side="buy_to_cover", qty=10)
        assert a.side == "buy_to_cover"

    def test_round_trip(self):
        a = PlaceOrderArgs(symbol="X", side="sell_short", qty=10, stop_loss=110, take_profit=85)
        assert PlaceOrderArgs.model_validate_json(a.model_dump_json()) == a
