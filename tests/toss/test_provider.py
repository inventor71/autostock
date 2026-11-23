from datetime import date, datetime

import pytest

from src.core.exceptions import DataProviderError
from src.core.types import TimeFrame
from src.data.providers.toss_provider import TossDataProvider


def candle(timestamp, price=100, currency="USD"):
    return {"timestamp": timestamp, "openPrice": str(price), "highPrice": str(price + 2),
            "lowPrice": str(price - 1), "closePrice": str(price + 1), "volume": "10", "currency": currency}


def test_quote_batches_and_currency(client_factory):
    def route(r):
        return [{"symbol": s, "lastPrice": "101.5", "currency": "USD"} for s in r.url.params["symbols"].split(",")]

    client, calls = client_factory(route)
    provider = TossDataProvider(client)
    symbols = [f"SYM{i}" for i in range(201)]
    assert len(provider.get_latest_prices(symbols)) == 201
    assert sum(r.url.path == "/api/v1/prices" for r in calls) == 2
    assert provider.get_latest_price("aapl") == 101.5


def test_quote_missing_or_wrong_currency_is_not_silently_used(client_factory):
    client, _ = client_factory(lambda r: [{"symbol": "005930", "lastPrice": "72000", "currency": "KRW"}])
    with pytest.raises(DataProviderError, match="currency"):
        TossDataProvider(client).get_latest_price("005930")
    missing, _ = client_factory(lambda r: [])
    with pytest.raises(DataProviderError, match="requested quote"):
        TossDataProvider(missing).get_latest_price("AAPL")


def test_minute_close_timestamp_becomes_start_and_no_lookahead(client_factory):
    rows = [candle(f"2026-03-25T09:{minute:02d}:00-04:00", minute) for minute in (33, 32, 31)]
    client, _ = client_factory(lambda r: {"candles": rows, "nextBefore": None})
    frame = TossDataProvider(client).get_bars(
        "AAPL", TimeFrame.MINUTE_1, end=datetime.fromisoformat("2026-03-25T09:32:00-04:00"),
    )
    assert [stamp.strftime("%H:%M") for stamp in frame.index] == ["09:30", "09:31"]
    assert list(frame["open"]) == [31, 32]
    assert str(frame.index.tz) == "America/New_York"


def test_resampling_drops_incomplete_bucket(client_factory):
    rows = [candle(f"2026-03-25T09:{minute:02d}:00-04:00", minute) for minute in range(36, 30, -1)]
    client, _ = client_factory(lambda r: {"candles": rows, "nextBefore": None})
    frame = TossDataProvider(client).get_bars(
        "AAPL", TimeFrame.MINUTE_5, end=datetime.fromisoformat("2026-03-25T09:36:00-04:00"),
    )
    assert len(frame) == 1
    assert frame.index[0].strftime("%H:%M") == "09:30"
    assert frame.iloc[0].to_dict() == {"open": 31, "high": 37, "low": 30, "close": 36, "volume": 50}


def test_resampling_does_not_invent_missing_start_of_fetched_bucket(client_factory):
    rows = [candle(f"2026-03-25T09:{minute:02d}:00-04:00") for minute in (35, 34, 33)]
    client, _ = client_factory(lambda r: {"candles": rows, "nextBefore": None})
    frame = TossDataProvider(client).get_bars(
        "AAPL", TimeFrame.MINUTE_5, end=datetime.fromisoformat("2026-03-25T09:35:00-04:00"),
    )
    assert frame.empty


def test_inclusive_pagination_is_deduplicated(client_factory):
    cursor = "2026-03-25T09:32:00-04:00"

    def route(r):
        if r.url.params["before"] == cursor:
            return {"candles": [candle(cursor), candle("2026-03-25T09:31:00-04:00")], "nextBefore": None}
        return {"candles": [candle("2026-03-25T09:33:00-04:00"), candle(cursor)], "nextBefore": cursor}

    client, calls = client_factory(route)
    frame = TossDataProvider(client).get_bars(
        "AAPL", TimeFrame.MINUTE_1, end=datetime.fromisoformat("2026-03-25T09:34:00-04:00"), limit=3,
    )
    assert len(frame) == 3 and frame.index.is_unique and frame.index.is_monotonic_increasing
    assert sum(r.url.path == "/api/v1/candles" for r in calls) == 2


def test_daily_timestamps_use_us_trading_date_and_exclude_incomplete_day(client_factory):
    rows = [candle("2026-03-25T13:00:00+09:00"), candle("2026-03-24T13:00:00+09:00")]
    client, _ = client_factory(lambda r: {"candles": rows, "nextBefore": None})
    frame = TossDataProvider(client).get_bars("AAPL", end=datetime.fromisoformat("2026-03-25T12:00:00-04:00"))
    assert list(frame.index.date) == [date(2026, 3, 24)]
    assert frame.index[0].hour == 0


def test_daily_absent_day_does_not_fall_back_to_old_close(client_factory):
    client, _ = client_factory(lambda r: {"candles": [candle("2026-03-24T13:00:00+09:00")], "nextBefore": None})
    assert TossDataProvider(client).get_daily_bar("AAPL", date(2026, 3, 25)) is None


def test_kr_data_is_explicit_and_separate_from_us_broker(client_factory):
    client, _ = client_factory(lambda r: {"candles": [candle("2026-03-24T00:00:00+09:00", 72000, "KRW")], "nextBefore": None})
    frame = TossDataProvider(client, market="KR").get_bars("005930", end=datetime(2026, 3, 25))
    assert str(frame.index.tz) == "Asia/Seoul"
    assert frame.iloc[0]["open"] == 72000


def test_no_advance_in_pagination_fails(client_factory):
    client, _ = client_factory(lambda r: {"candles": [candle("2026-03-25T09:31:00-04:00")], "nextBefore": "2026-03-25T09:31:00-04:00"})
    with pytest.raises(DataProviderError, match="pagination"):
        TossDataProvider(client).get_bars("AAPL", TimeFrame.MINUTE_1, limit=2)


@pytest.mark.parametrize("kwargs", [{"timeframe": TimeFrame.WEEK_1}, {"limit": 0}, {"limit": 100001}])
def test_invalid_queries_fail_before_http(client_factory, kwargs):
    client, calls = client_factory(lambda r: pytest.fail("Must not query HTTP"))
    with pytest.raises(DataProviderError):
        TossDataProvider(client).get_bars("AAPL", **kwargs)
    assert calls == []
