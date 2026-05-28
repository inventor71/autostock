"""Market data tool functions for the PM agent.

Each function takes an injectable data source (a ``BaseDataProvider`` for the
bar-based tools, a ticker factory for fundamentals, a news provider for news) so
it can be unit-tested with synthetic data and no network. ``__main__`` wires the
real yfinance-backed providers and prints the returned dict/list as JSON.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from src.strategy.ml.feature_eng import build_technical_features


def _round(value: Any, ndigits: int = 4) -> Any:
    """Round floats for compact JSON; pass through None and non-floats."""
    if isinstance(value, float):
        return round(value, ndigits)
    return value


def _pct_change(bars: pd.DataFrame, periods: int) -> float | None:
    if len(bars) < periods + 1:
        return None
    past = bars["close"].iloc[-periods - 1]
    if past == 0:
        return None
    return round((bars["close"].iloc[-1] / past - 1) * 100, 2)


def _latest_features(bars: pd.DataFrame) -> pd.Series | None:
    """Latest technical-feature row, or None when there is not enough data."""
    try:
        feats = build_technical_features(bars)
    except Exception:
        return None
    if feats.empty:
        return None
    return feats.iloc[-1]


def quote(symbol: str, provider, limit: int = 60) -> dict:
    """Latest price and recent price action for a symbol."""
    bars = provider.get_bars(symbol, limit=limit)
    if bars is None or bars.empty:
        return {"symbol": symbol, "error": "no data"}
    last = bars.iloc[-1]
    return {
        "symbol": symbol.upper(),
        "asof": str(bars.index[-1]),
        "price": _round(float(last["close"]), 2),
        "open": _round(float(last["open"]), 2),
        "high": _round(float(last["high"]), 2),
        "low": _round(float(last["low"]), 2),
        "volume": int(last["volume"]),
        "change_1d_pct": _pct_change(bars, 1),
        "change_5d_pct": _pct_change(bars, 5),
        "change_20d_pct": _pct_change(bars, 20),
        "bars": len(bars),
    }


def indicators(symbol: str, provider, limit: int = 120) -> dict:
    """Technical indicators for a symbol (RSI/MACD/Bollinger/SMA/ATR).

    ATR is reported both as a fraction of price (``atr_pct``) and as absolute
    dollars per share (``atr_abs``) — the latter is what position sizing /
    stop placement consume downstream.
    """
    bars = provider.get_bars(symbol, limit=limit)
    if bars is None or bars.empty:
        return {"symbol": symbol, "error": "no data"}
    row = _latest_features(bars)
    if row is None:
        return {"symbol": symbol, "error": "insufficient data for indicators"}
    close = float(bars["close"].iloc[-1])
    atr_pct = float(row["atr_14"])
    return {
        "symbol": symbol.upper(),
        "close": _round(close, 2),
        "rsi_14": _round(float(row["rsi_14"]), 1),
        "macd": _round(float(row["macd"])),
        "macd_signal": _round(float(row["macd_signal"])),
        "macd_hist": _round(float(row["macd_hist"])),
        "bb_pct_b": _round(float(row["bb_pct_b"]), 3),
        "price_to_sma20_pct": _round(float(row["price_to_sma20"]) * 100, 2),
        "price_to_sma50_pct": _round(float(row["price_to_sma50"]) * 100, 2),
        "sma20_to_sma50_pct": _round(float(row["sma20_to_sma50"]) * 100, 2),
        "volatility_20d_pct": _round(float(row["volatility_20d"]) * 100, 2),
        "volume_ratio": _round(float(row["volume_ratio"]), 2),
        "atr_pct": _round(atr_pct * 100, 2),
        "atr_abs": _round(atr_pct * close, 2),
    }


def scoreboard(symbols: list[str], provider, limit: int = 120) -> list[dict]:
    """One compact row per symbol: a cheap wide-angle scan of the universe.

    The agent reads this to choose which names deserve deep work — Python does
    not pre-select candidates.
    """
    rows: list[dict] = []
    for symbol in symbols:
        try:
            bars = provider.get_bars(symbol, limit=limit)
        except Exception as exc:  # one bad symbol must not sink the scan
            rows.append({"symbol": symbol.upper(), "error": str(exc)})
            continue
        if bars is None or bars.empty:
            rows.append({"symbol": symbol.upper(), "error": "no data"})
            continue

        recent_high = float(bars["high"].tail(20).max())
        close = float(bars["close"].iloc[-1])
        row = _latest_features(bars)
        rows.append({
            "symbol": symbol.upper(),
            "close": _round(close, 2),
            "chg_1d": _pct_change(bars, 1),
            "chg_5d": _pct_change(bars, 5),
            "chg_20d": _pct_change(bars, 20),
            "rsi_14": _round(float(row["rsi_14"]), 1) if row is not None else None,
            "macd_hist": _round(float(row["macd_hist"])) if row is not None else None,
            "vol_ratio": _round(float(row["volume_ratio"]), 2) if row is not None else None,
            "dist_high_20d_pct": _round((close / recent_high - 1) * 100, 2) if recent_high else None,
        })
    return rows


# yfinance fundamentals fields worth surfacing to the agent.
_FUNDAMENTAL_KEYS = (
    "longName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
    "priceToBook", "profitMargins", "revenueGrowth", "earningsGrowth",
    "dividendYield", "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "targetMeanPrice", "recommendationKey",
)


def fundamentals(symbol: str, ticker_factory: Callable[[str], Any] | None = None) -> dict:
    """Valuation / sector snapshot from yfinance ``Ticker.info``."""
    if ticker_factory is None:
        import yfinance as yf
        ticker_factory = yf.Ticker
    try:
        info = ticker_factory(symbol).info or {}
    except Exception as exc:
        return {"symbol": symbol.upper(), "error": str(exc)}
    return {"symbol": symbol.upper(), **{k: info.get(k) for k in _FUNDAMENTAL_KEYS}}


def news(symbol: str, news_provider=None, limit: int = 8) -> dict:
    """Recent news headlines for a symbol, with links."""
    if news_provider is None:
        from src.data.providers.news_provider import YFinanceNewsProvider
        news_provider = YFinanceNewsProvider()
    items = news_provider.get_news(symbol, limit=limit)
    return {
        "symbol": symbol.upper(),
        "news": [
            {
                "title": it.title,
                "publisher": it.publisher,
                "published_at": it.published_at.isoformat() if it.published_at else None,
                "link": it.link,
                "sentiment": it.sentiment_score,
            }
            for it in items
        ],
    }


def _side_str(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def account(broker) -> dict:
    """Live broker truth: equity/cash, held positions with P&L, resting orders.

    Read-only. Lets the morning/intraday turns ground decisions in what the
    account actually holds and what protective (stop/target) or pending-entry
    orders are live at the broker — not the agent's journal recollection, which
    can lag a fill or a triggered protective leg.
    """
    state = broker.get_portfolio_state()

    orders_error: str | None = None
    try:
        open_orders = broker.get_open_orders()
    except Exception as exc:  # broker truth is best-effort; positions still useful
        open_orders, orders_error = [], str(exc)

    positions = []
    for p in sorted(state.positions.values(), key=lambda x: x.symbol):
        unreal_pct = (
            (p.current_price / p.avg_entry_price - 1) * 100 if p.avg_entry_price else None
        )
        positions.append({
            "symbol": p.symbol,
            "qty": _round(p.qty),
            "avg_entry": _round(p.avg_entry_price, 2),
            "price": _round(p.current_price, 2),
            "unrealized_pnl": _round(p.unrealized_pnl, 2),
            "unrealized_pct": _round(unreal_pct, 2) if unreal_pct is not None else None,
            "market_value": _round(p.market_value, 2),
        })

    invested = sum(p.market_value for p in state.positions.values())
    out: dict[str, Any] = {
        "equity": _round(state.equity, 2),
        "cash": _round(state.cash, 2),
        "invested": _round(invested, 2),
        "invested_pct": _round(invested / state.equity * 100, 2) if state.equity else None,
        "position_count": len(positions),
        "positions": positions,
        "open_orders": [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": _side_str(o.side),
                "type": _side_str(o.order_type),
                "qty": _round(o.qty),
                "limit": _round(o.limit_price, 2) if o.limit_price is not None else None,
                "stop": _round(o.stop_price, 2) if o.stop_price is not None else None,
            }
            for o in open_orders
        ],
    }
    if orders_error is not None:
        out["open_orders_error"] = orders_error
    return out
