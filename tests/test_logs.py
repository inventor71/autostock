from src.agent.equity_log import snapshot
from src.agent.trades_log import match_round_trips
from src.agent.turn_log import read_turns, record_turn
from src.core.models import PortfolioState, Position


# --------------------------------------------------------------------------- #
# Closed round-trip reconstruction (FIFO)
# --------------------------------------------------------------------------- #
class TestRoundTrips:
    def _fill(self, sym, side, qty, price, ts):
        return {"symbol": sym, "side": side, "qty": qty, "price": price, "ts": ts}

    def test_full_round_trip(self):
        fills = [
            self._fill("AAPL", "buy", 10, 100.0, "2026-01-01T10:00"),
            self._fill("AAPL", "sell", 10, 110.0, "2026-01-02T10:00"),
        ]
        trades = match_round_trips(fills)
        assert len(trades) == 1
        t = trades[0]
        assert t["entry_price"] == 100.0 and t["exit_price"] == 110.0
        assert t["realized_pnl"] == 100.0
        assert t["return_pct"] == 10.0

    def test_partial_close_leaves_rest_open(self):
        fills = [
            self._fill("AAPL", "buy", 10, 100.0, "t1"),
            self._fill("AAPL", "sell", 4, 110.0, "t2"),
        ]
        trades = match_round_trips(fills)
        assert len(trades) == 1
        assert trades[0]["qty"] == 4 and trades[0]["realized_pnl"] == 40.0

    def test_fifo_across_lots(self):
        fills = [
            self._fill("AAPL", "buy", 5, 100.0, "t1"),
            self._fill("AAPL", "buy", 5, 120.0, "t2"),
            self._fill("AAPL", "sell", 8, 130.0, "t3"),
        ]
        trades = match_round_trips(fills)
        assert len(trades) == 2
        assert trades[0]["entry_price"] == 100.0 and trades[0]["realized_pnl"] == 150.0  # 5 @ (130-100)
        assert trades[1]["entry_price"] == 120.0 and trades[1]["realized_pnl"] == 30.0   # 3 @ (130-120)

    def test_open_position_yields_no_trade(self):
        assert match_round_trips([self._fill("AAPL", "buy", 10, 100.0, "t1")]) == []


# --------------------------------------------------------------------------- #
# Turn telemetry
# --------------------------------------------------------------------------- #
class TestTurnLog:
    def test_record_extracts_metrics(self, tmp_path):
        raw = {
            "total_cost_usd": 0.042, "duration_ms": 280000, "num_turns": 12,
            "usage": {"input_tokens": 1200, "output_tokens": 340},
        }
        path = tmp_path / "turns.jsonl"
        rec = record_turn(path, turn_type="research", model="sonnet", num_decisions=2, raw=raw)
        assert rec["turn_type"] == "research"
        assert rec["cost_usd"] == 0.042
        assert rec["num_decisions"] == 2
        assert rec["input_tokens"] == 1200
        assert len(read_turns(path)) == 1

    def test_record_tolerates_empty_raw(self, tmp_path):
        rec = record_turn(tmp_path / "turns.jsonl", turn_type="intraday", model="sonnet", num_decisions=0, raw=None)
        assert rec["cost_usd"] is None and rec["num_decisions"] == 0


# --------------------------------------------------------------------------- #
# Equity snapshot enrichment
# --------------------------------------------------------------------------- #
class TestEquitySnapshotEnrich:
    def _pf(self):
        return PortfolioState(
            cash=90000.0, equity=100000.0,
            positions={"AAPL": Position(symbol="AAPL", qty=10, avg_entry_price=300.0,
                                        current_price=310.0, unrealized_pnl=100.0, market_value=3100.0)},
        )

    def test_exposure_fields(self):
        snap = snapshot(self._pf())
        assert snap["invested_pct"] == 3.1
        assert snap["cash_pct"] == 90.0
        assert snap["largest_pos_pct"] == 3.1

    def test_benchmark_recorded(self):
        snap = snapshot(self._pf(), benchmark={"SPY": 750.6, "VIX": 16.6, "QQQ": None})
        assert snap["benchmark"] == {"SPY": 750.6, "VIX": 16.6}  # None dropped


# --------------------------------------------------------------------------- #
# Fill parsing filters (drop pre-experiment + penny/test fills)
# --------------------------------------------------------------------------- #
class TestFillFiltering:
    def _order(self, sym, side, qty, price, dt):
        from types import SimpleNamespace
        return SimpleNamespace(
            symbol=sym, side=side, qty=qty, filled_qty=qty,
            filled_avg_price=price, filled_at=dt, id="x",
        )

    def test_drops_pre_experiment_and_penny_fills(self):
        from datetime import datetime, timezone
        from src.agent.trades_log import _alpaca_fills

        orders = [
            self._order("PFE", "sell", 1, 25.79, datetime(2026, 5, 26, 14, 42, tzinfo=timezone.utc)),  # pre-start
            self._order("XYZ", "buy", 1, 10.0, datetime(2026, 5, 28, 15, 0, tzinfo=timezone.utc)),     # penny
            self._order("AAPL", "buy", 10, 309.0, datetime(2026, 5, 27, 13, 3, tzinfo=timezone.utc)),  # legit
        ]

        class FakeClient:
            def get_orders(self, filter=None):
                return orders

        fills = _alpaca_fills(FakeClient(), since="2026-05-27", min_notional=50.0)
        assert {f["symbol"] for f in fills} == {"AAPL"}
