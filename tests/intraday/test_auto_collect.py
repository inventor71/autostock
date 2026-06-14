"""F82: gap-aware intraday auto-collection (backfill window + universe sweep + EOD append).

Pure-logic + orchestration tests over a real (Parquet) IntradayFeatureStore and a
fake bar provider — no network, no scheduler.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.data.intraday.auto import (
    CollectionConfig,
    backfill_universe,
    backfill_window,
    collect_today,
    last_session_date,
)
from src.data.intraday.store import IntradayFeatureStore


def _bars(dates, *, bars_per_session=6, base=100.0) -> pd.DataFrame:
    """Synthetic intraday frame: one RTH-ish 5m session per date (>= min_bars)."""
    frames = []
    for di, d in enumerate(dates):
        start = pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=30)
        idx = pd.date_range(start, periods=bars_per_session, freq="5min")
        o = base + di
        frames.append(
            pd.DataFrame(
                {
                    "open": [o] * bars_per_session,
                    "high": [o + 1] * bars_per_session,
                    "low": [o - 1] * bars_per_session,
                    "close": [o + 0.5] * bars_per_session,
                    "volume": [1000] * bars_per_session,
                },
                index=idx,
            )
        )
    return pd.concat(frames)


class FakeProvider:
    """Returns a fixed frame per symbol; range/limit args are ignored (the real
    range fetch is the provider's concern — here we test the orchestration)."""

    def __init__(self, bars_by_symbol, *, fail=()):
        self._bars = bars_by_symbol
        self._fail = set(fail)
        self.calls: list[tuple] = []

    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=None):
        self.calls.append((symbol, start, end, limit))
        if symbol in self._fail:
            raise RuntimeError(f"boom {symbol}")
        return self._bars[symbol]


# --------------------------------------------------------------------------- #
# backfill_window
# --------------------------------------------------------------------------- #
class TestBackfillWindow:
    def test_unstored_returns_full_history(self):
        today = date(2026, 6, 10)
        w = backfill_window(None, today=today, backfill_years=3)
        assert w == (today - timedelta(days=3 * 365), today)

    def test_stale_returns_incremental(self):
        today = date(2026, 6, 10)
        last = today - timedelta(days=5)
        assert backfill_window(last, today=today, backfill_years=3) == (
            last + timedelta(days=1), today,
        )

    def test_current_skips(self):
        today = date(2026, 6, 10)
        assert backfill_window(today, today=today, backfill_years=3) is None

    def test_yesterday_is_current_enough(self):
        # last == today-1 → not "< today-1" → skip (today's session not closed yet).
        today = date(2026, 6, 10)
        assert backfill_window(today - timedelta(days=1), today=today, backfill_years=3) is None


# --------------------------------------------------------------------------- #
# CollectionConfig
# --------------------------------------------------------------------------- #
class TestCollectionConfig:
    def test_defaults_when_block_absent(self):
        cfg = CollectionConfig.from_yaml({})
        assert cfg.enabled is True and cfg.backfill_years == 3
        assert cfg.provider == "alpaca" and cfg.timeframe == "5m"

    def test_explicit_values(self):
        cfg = CollectionConfig.from_yaml(
            {"intraday_collection": {"enabled": False, "backfill_years": 5,
                                     "provider": "yfinance", "timeframe": "15m"}}
        )
        assert cfg.enabled is False and cfg.backfill_years == 5
        assert cfg.provider == "yfinance" and cfg.timeframe == "15m"


# --------------------------------------------------------------------------- #
# backfill_universe / last_session_date
# --------------------------------------------------------------------------- #
class TestBackfillUniverse:
    def _dates(self, today):
        return [today - timedelta(days=2), today - timedelta(days=1), today]

    def test_fills_empty_store_then_skips_when_current(self, tmp_path):
        today = date(2026, 6, 10)
        store = IntradayFeatureStore(root=tmp_path)
        provider = FakeProvider(
            {"AAPL": _bars(self._dates(today)), "MSFT": _bars(self._dates(today))}
        )
        first = backfill_universe(
            provider, store, ["AAPL", "MSFT"], today=today, backfill_years=3
        )
        assert first == {"AAPL": 3, "MSFT": 3}
        assert last_session_date(store, "AAPL") == today

        # Re-run: every symbol is current → window None → no fetch, 0 written.
        provider.calls.clear()
        second = backfill_universe(
            provider, store, ["AAPL", "MSFT"], today=today, backfill_years=3
        )
        assert second == {"AAPL": 0, "MSFT": 0}
        assert provider.calls == []  # skipped without touching the provider

    def test_failing_symbol_isolated(self, tmp_path):
        today = date(2026, 6, 10)
        store = IntradayFeatureStore(root=tmp_path)
        provider = FakeProvider(
            {"AAPL": _bars(self._dates(today)), "BAD": _bars(self._dates(today))},
            fail=["BAD"],
        )
        res = backfill_universe(
            provider, store, ["AAPL", "BAD"], today=today, backfill_years=3
        )
        assert res["AAPL"] == 3 and res["BAD"] == 0
        assert last_session_date(store, "BAD") is None  # nothing persisted for BAD


# --------------------------------------------------------------------------- #
# collect_today
# --------------------------------------------------------------------------- #
class TestCollectToday:
    def test_appends_recent_sessions(self, tmp_path):
        today = date(2026, 6, 10)
        store = IntradayFeatureStore(root=tmp_path)
        dates = [today - timedelta(days=1), today]
        provider = FakeProvider({"AAPL": _bars(dates), "MSFT": _bars(dates)})
        res = collect_today(provider, store, ["AAPL", "MSFT"], today=today)
        assert res == {"AAPL": 2, "MSFT": 2}
        assert last_session_date(store, "AAPL") == today
        # date-range path: start/end passed (no bare limit), end spans past today.
        assert all(c[1] is not None and c[3] is None for c in provider.calls)
        assert all(c[2].date() > today for c in provider.calls)  # end includes today

    def test_idempotent_on_rerun(self, tmp_path):
        today = date(2026, 6, 10)
        store = IntradayFeatureStore(root=tmp_path)
        provider = FakeProvider({"AAPL": _bars([today])})
        collect_today(provider, store, ["AAPL"], today=today)
        collect_today(provider, store, ["AAPL"], today=today)  # same day again
        assert len(store.read(["AAPL"])) == 1  # last-write-wins, no duplicate


# --------------------------------------------------------------------------- #
# Daemon wiring: AgentTradingMode._setup_intraday_collection
# --------------------------------------------------------------------------- #
def _make_mode(tmp_path, provider, monkeypatch):
    """Minimal AgentTradingMode with stubbed orchestrator/executor (steering off)."""
    from types import SimpleNamespace

    from src.trading.modes.agent import AgentTradingMode

    # __init__ sets os.environ["AGENT_JOURNAL_ROOT"]; register it so monkeypatch
    # restores the original on teardown (else it leaks into other tests).
    monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
    executor = SimpleNamespace(
        journal=SimpleNamespace(root=tmp_path),
        data_provider=provider,
        universe={"AAPL", "MSFT"},
    )
    return AgentTradingMode(SimpleNamespace(), executor, steering=None)


class TestAgentWiring:
    def test_gate_off_does_not_wire(self, tmp_path, monkeypatch):
        import config.config as cc

        monkeypatch.setattr(
            cc, "load_yaml_config",
            lambda _p: {"intraday_collection": {"enabled": False}},
        )
        mode = _make_mode(tmp_path, FakeProvider({}), monkeypatch)
        mode._setup_intraday_collection()
        assert mode._intraday_collect_enabled is False
        assert mode._intraday_backfill_thread is None

    def test_gate_on_backfills_in_thread(self, tmp_path, monkeypatch):
        import config.config as cc

        # provider=yfinance → reuse the (fake) daemon provider, no alpaca keys needed.
        monkeypatch.setattr(
            cc, "load_yaml_config",
            lambda _p: {"intraday_collection": {"enabled": True, "provider": "yfinance",
                                                "backfill_years": 1, "timeframe": "5m"}},
        )
        dates = [date(2026, 5, 1), date(2026, 5, 2)]
        provider = FakeProvider({"AAPL": _bars(dates), "MSFT": _bars(dates)})
        mode = _make_mode(tmp_path, provider, monkeypatch)
        mode._setup_intraday_collection()

        assert mode._intraday_collect_enabled is True
        mode._intraday_backfill_thread.join(timeout=10)
        assert not mode._intraday_backfill_thread.is_alive()
        # backfill actually populated the store via the background thread.
        assert last_session_date(mode._intraday_store, "AAPL") == date(2026, 5, 2)

    def test_wiring_failclosed_on_bad_config(self, tmp_path, monkeypatch):
        import config.config as cc

        def _boom(_p):
            raise RuntimeError("config read failed")

        monkeypatch.setattr(cc, "load_yaml_config", _boom)
        mode = _make_mode(tmp_path, FakeProvider({}), monkeypatch)
        mode._setup_intraday_collection()  # must not raise
        assert mode._intraday_collect_enabled is False
