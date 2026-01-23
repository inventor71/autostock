from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_returns(equity_curve: pd.Series) -> pd.Series:
    """Calculate daily returns from equity curve."""
    return equity_curve.pct_change().dropna()


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods: int = 252) -> float:
    """Annualized Sharpe ratio."""
    if returns.std() == 0:
        return 0.0
    excess = returns.mean() - risk_free_rate / periods
    return float(excess / returns.std() * np.sqrt(periods))


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum drawdown as a positive percentage."""
    peak = equity_curve.expanding().max()
    drawdown = (equity_curve - peak) / peak
    return float(abs(drawdown.min()))


def total_return(equity_curve: pd.Series) -> float:
    """Total return as a percentage."""
    if equity_curve.iloc[0] == 0:
        return 0.0
    return float((equity_curve.iloc[-1] / equity_curve.iloc[0] - 1) * 100)


def win_rate(trades: list[dict]) -> float:
    """Percentage of winning trades."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    return wins / len(trades)


def profit_factor(trades: list[dict]) -> float:
    """Ratio of gross profit to gross loss."""
    gross_profit = sum(t["pnl"] for t in trades if t.get("pnl", 0) > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t.get("pnl", 0) < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods: int = 252) -> float:
    """Annualized Sortino ratio (only downside deviation)."""
    downside = returns[returns < 0]
    if downside.std() == 0:
        return 0.0
    excess = returns.mean() - risk_free_rate / periods
    return float(excess / downside.std() * np.sqrt(periods))


def calmar_ratio(equity_curve: pd.Series, periods: int = 252) -> float:
    """Calmar ratio: annualized return / max drawdown."""
    returns = calculate_returns(equity_curve)
    annual_return = returns.mean() * periods
    mdd = max_drawdown(equity_curve)
    if mdd == 0:
        return 0.0
    return float(annual_return / mdd)


def generate_report(
    equity_curve: pd.Series,
    trades: list[dict],
    initial_capital: float,
) -> dict:
    """Generate a comprehensive performance report."""
    returns = calculate_returns(equity_curve)
    return {
        "total_return_pct": total_return(equity_curve),
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "max_drawdown_pct": max_drawdown(equity_curve) * 100,
        "calmar_ratio": calmar_ratio(equity_curve),
        "total_trades": len(trades),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "final_capital": float(equity_curve.iloc[-1]),
        "initial_capital": initial_capital,
    }
