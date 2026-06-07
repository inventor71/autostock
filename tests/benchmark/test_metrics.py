from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from src.benchmark.metrics import compute_metrics
from src.benchmark.models import EquitySnapshot


def series(strategy: str, equities: list[float], start=datetime(2026, 1, 1)) -> list[EquitySnapshot]:
    return [
        EquitySnapshot(
            ts=start + timedelta(days=i), strategy=strategy,
            account_masked="x", equity=e, cash=0.0, position_count=0,
        )
        for i, e in enumerate(equities)
    ]


def test_cum_return_and_alpha():
    by = {
        "llm": series("llm", [1000.0, 1100.0, 1200.0]),       # +20%
        "rsi": series("rsi", [1000.0, 1000.0, 1100.0]),       # +10%
    }
    m = compute_metrics(by)
    assert m.llm is not None
    assert abs(m.llm.cum_return - 0.2) < 1e-9
    assert abs(m.alpha["rsi"] - 0.1) < 1e-9  # llm 20% - rsi 10%


def test_max_drawdown_negative():
    by = {"llm": series("llm", [1000.0, 1200.0, 600.0, 900.0])}
    m = compute_metrics(by)
    # peak 1200 -> trough 600 = -50%
    assert abs(m.llm.max_drawdown - (-0.5)) < 1e-9


def test_no_llm_series_means_no_alpha():
    by = {"rsi": series("rsi", [1000.0, 1100.0])}
    m = compute_metrics(by)
    assert m.llm is None
    assert m.alpha == {}


def test_common_window_truncation():
    # rsi starts a day later; comparison must use the overlap only.
    by = {
        "llm": series("llm", [1000.0, 1100.0, 1210.0], start=datetime(2026, 1, 1)),
        "rsi": series("rsi", [1000.0, 1050.0], start=datetime(2026, 1, 2)),
    }
    m = compute_metrics(by)
    assert m.window_start == datetime(2026, 1, 2)
    assert m.window_end == datetime(2026, 1, 3)
    # llm within window: 1100 -> 1210 = +10%
    assert abs(m.llm.cum_return - 0.1) < 1e-9


def test_single_point_is_zero_return():
    by = {"llm": series("llm", [1000.0])}
    m = compute_metrics(by)
    assert m.llm.cum_return == 0.0
    assert m.llm.volatility == 0.0
    assert m.llm.sharpe == 0.0


@given(
    equities=st.lists(
        st.floats(min_value=1.0, max_value=1e7, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=40,
    )
)
@settings(max_examples=100)
def test_compute_is_pure_deterministic(equities):
    # BR-6 / NFR-4: identical input -> identical output, no hidden state.
    by = {"llm": series("llm", equities)}
    a = compute_metrics(by)
    b = compute_metrics(by)
    assert a.model_dump() == b.model_dump()
    assert a.llm.max_drawdown <= 0.0  # drawdown is never positive
