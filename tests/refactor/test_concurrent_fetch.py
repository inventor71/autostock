"""R2 C-3p / C-4 equivalence tests: concurrent fetch preserves value + isolation.

These changes only overlap network calls; the per-symbol values and the
single-symbol-failure isolation must be identical to the old sequential loops.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.agent.equity_log import fetch_benchmark
from src.agent.tools import market
from src.data.prices import fetch_latest_prices


class _PriceProvider:
    """Returns a fixed price per symbol; raises for symbols in ``fail``."""

    def __init__(self, prices: dict[str, float], fail: set[str] | None = None):
        self._prices = prices
        self._fail = fail or set()
        self.calls: list[str] = []

    def get_latest_price(self, symbol: str) -> float:
        self.calls.append(symbol)
        if symbol in self._fail:
            raise RuntimeError(f"boom {symbol}")
        return self._prices[symbol]


def test_fetch_latest_prices_values_and_isolation():
    p = _PriceProvider({"AAA": 10.0, "BBB": 20.0, "CCC": 30.0}, fail={"BBB"})
    out = fetch_latest_prices(p, ["AAA", "BBB", "CCC"])
    # Every symbol present; failing one → None; others exact value.
    assert out == {"AAA": 10.0, "BBB": None, "CCC": 30.0}
    # Same set of calls as a sequential loop would make (order-independent).
    assert sorted(p.calls) == ["AAA", "BBB", "CCC"]


def test_fetch_latest_prices_single_symbol_path():
    p = _PriceProvider({"AAA": 42.0})
    assert fetch_latest_prices(p, ["AAA"]) == {"AAA": 42.0}
    assert fetch_latest_prices(p, []) == {}


def test_fetch_benchmark_skips_failures_and_strips_caret():
    p = _PriceProvider({"SPY": 500.0, "QQQ": 400.0, "^VIX": 15.0}, fail={"QQQ"})
    out = fetch_benchmark(p, ("SPY", "QQQ", "^VIX"))
    # QQQ failed → skipped; ^VIX caret stripped in the key; values exact.
    assert out == {"SPY": 500.0, "VIX": 15.0}


class _BarsProvider:
    """Deterministic bars per symbol; raises for symbols in ``fail``."""

    def __init__(self, fail: set[str] | None = None):
        self._fail = fail or set()

    def get_bars(self, symbol: str, limit: int = 120) -> pd.DataFrame:
        if symbol in self._fail:
            raise RuntimeError(f"no data {symbol}")
        n = 80
        base = float(sum(ord(c) for c in symbol) % 50 + 50)
        close = [base + i * 0.1 for i in range(n)]
        return pd.DataFrame(
            {"open": close, "high": [c * 1.01 for c in close],
             "low": [c * 0.99 for c in close], "close": close,
             "volume": [1_000_000] * n},
            index=pd.date_range("2023-01-01", periods=n, freq="D"),
        )


def test_scoreboard_preserves_order_value_and_isolation():
    syms = ["AAA", "BAD", "CCC", "DDD"]
    prov = _BarsProvider(fail={"BAD"})
    rows = market.scoreboard(syms, prov)

    # Order preserved 1:1 with input.
    assert [r["symbol"] for r in rows] == [s.upper() for s in syms]
    # The failing symbol yields an error row; the rest are full rows.
    assert "error" in rows[1] and rows[1]["symbol"] == "BAD"
    assert all("error" not in rows[i] for i in (0, 2, 3))
    # Deterministic: same call twice → identical output (value + order).
    assert market.scoreboard(syms, prov) == rows
