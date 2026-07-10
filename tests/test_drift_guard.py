"""F96 — entry drift guard (RiskManager).

A momentum entry the agent submits at market (``limit`` = None) has no price level
of its own, so between the decision and the (possibly ~50-min-later) execution the
fill can land far from where the agent decided. The orchestrator stamps the
decision-time price as ``ref_price``; the guard uses it (or the LLM's explicit
``entry`` when present) as the anchor and, once the price has run adversely past
the anchor by more than ``entry_drift_guard_atr * ATR``, downgrades the MARKET to
a LIMIT capped at ``anchor ± band`` — bounding the worst fill. No anchor / no ATR /
disabled keeps the pre-F96 behaviour byte-for-byte.
"""

from __future__ import annotations

from src.core.models import PortfolioState, TradeSignal
from src.core.types import OrderClass, OrderType, Signal
from src.risk.manager import RiskManager


def _rm(**kw):
    base = dict(
        max_position_pct=0.5, max_portfolio_risk=0.02, max_open_positions=10,
        max_stop_distance_pct=0.20, atr_stop_multiple=3.0, default_risk_reward=2.5,
        use_bracket_orders=True,
    )
    base.update(kw)
    return RiskManager(**base)


def _sig(signal, **meta_levels):
    key_levels = {k: meta_levels.get(k) for k in ("entry", "stop_loss", "take_profit")}
    metadata = {"key_levels": key_levels}
    for k in ("atr", "ref_price"):
        if k in meta_levels:
            metadata[k] = meta_levels[k]
    sym = "AAPL" if signal == Signal.BUY else "X"
    return TradeSignal(symbol=sym, signal=signal, confidence=1.0, metadata=metadata)


def _buy(**lv):
    return _sig(Signal.BUY, **lv)


def _short(**lv):
    return _sig(Signal.SELL_SHORT, **lv)


_P = PortfolioState(cash=100_000, equity=100_000)


class TestMarketBuyDriftGuard:
    """entry=None (market buy); anchor comes from ref_price."""

    def test_downgrades_to_capped_limit_when_price_ran_up(self):
        # ref_price=100, atr=2 -> band=1.0. price 103 > 101 -> LIMIT @ 101.
        order = _rm().evaluate_signal(_buy(stop_loss=95, take_profit=120, atr=2.0, ref_price=100.0), 103.0, _P)
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 101.0
        assert order.order_class == OrderClass.BRACKET
        assert order.stop_loss_price == 95.0

    def test_market_when_within_band(self):
        order = _rm().evaluate_signal(_buy(stop_loss=95, take_profit=120, atr=2.0, ref_price=100.0), 100.5, _P)
        assert order.order_type == OrderType.MARKET
        assert order.limit_price is None

    def test_exact_band_boundary_is_market(self):
        # price == anchor+band exactly is NOT "> band" -> stays MARKET.
        order = _rm().evaluate_signal(_buy(stop_loss=95, take_profit=120, atr=2.0, ref_price=100.0), 101.0, _P)
        assert order.order_type == OrderType.MARKET

    def test_no_atr_disables_guard(self):
        order = _rm().evaluate_signal(_buy(stop_loss=95, take_profit=120, ref_price=100.0), 110.0, _P)
        assert order.order_type == OrderType.MARKET

    def test_zero_knob_disables_guard(self):
        rm = _rm(entry_drift_guard_atr=0.0)
        order = rm.evaluate_signal(_buy(stop_loss=95, take_profit=120, atr=2.0, ref_price=100.0), 110.0, _P)
        assert order.order_type == OrderType.MARKET

    def test_no_anchor_at_all_is_market(self):
        # entry=None AND ref_price=None -> no anchor -> unchanged MARKET.
        order = _rm().evaluate_signal(_buy(stop_loss=95, take_profit=120, atr=2.0), 110.0, _P)
        assert order.order_type == OrderType.MARKET


class TestExplicitEntryUnchanged:
    """When the LLM gives an entry level, the pre-F96 behaviour must not change."""

    def test_buy_the_dip_limit_unchanged(self):
        order = _rm().evaluate_signal(_buy(entry=95, stop_loss=90, take_profit=115, atr=2.0), 100.0, _P)
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 95.0

    def test_entry_anchor_wins_over_ref_price(self):
        # entry present + price above entry -> buy-the-dip LIMIT@entry (NOT the
        # guard cap), even if a ref_price is also present.
        order = _rm().evaluate_signal(
            _buy(entry=100, stop_loss=95, take_profit=120, atr=2.0, ref_price=90.0), 103.0, _P
        )
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 100.0

    def test_entry_at_price_is_market(self):
        order = _rm().evaluate_signal(_buy(entry=100, stop_loss=95, take_profit=120, atr=2.0), 100.0, _P)
        assert order.order_type == OrderType.MARKET


class TestMarketShortDriftGuard:
    def test_downgrades_to_capped_limit_when_price_ran_down(self):
        # ref_price=100, atr=2 -> band=1.0. price 97 < 99 -> LIMIT @ 99.
        rm = _rm(shorting_enabled=True)
        order = rm.evaluate_signal(_short(stop_loss=108, take_profit=85, atr=2.0, ref_price=100.0), 97.0, _P)
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 99.0
        assert order.order_class == OrderClass.BRACKET
        assert order.stop_loss_price == 108.0

    def test_market_when_within_band(self):
        rm = _rm(shorting_enabled=True)
        order = rm.evaluate_signal(_short(stop_loss=108, take_profit=85, atr=2.0, ref_price=100.0), 99.5, _P)
        assert order.order_type == OrderType.MARKET

    def test_sell_the_rip_limit_unchanged(self):
        rm = _rm(shorting_enabled=True)
        order = rm.evaluate_signal(_short(entry=102, stop_loss=110, take_profit=90, atr=2.0), 100.0, _P)
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 102.0
