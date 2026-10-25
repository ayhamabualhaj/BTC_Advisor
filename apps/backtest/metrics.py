"""Pure backtest math: positions and daily returns in, profit and risk numbers out.

The strategy is daily: a buy signal at the close of day D means holding from that close
to the close of D+1. Consecutive buy days form one trade.
"""

from dataclasses import dataclass


@dataclass
class Performance:
    trade_count: int
    win_rate: float | None
    total_profit_pct: float
    max_drawdown_pct: float
    days_in_market: int


def equity_curve(positions, returns):
    """Account value after each day, starting from 1.0."""
    value, curve = 1.0, []
    for in_market, daily_return in zip(positions, returns):
        if in_market:
            value *= 1 + daily_return
        curve.append(value)
    return curve


def max_drawdown_pct(curve):
    """Largest fall from a peak, as a positive percent."""
    peak, worst = 1.0, 0.0
    for value in curve:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return worst * 100


def trade_returns(positions, returns):
    """Return of each run of consecutive in-market days."""
    trades, current = [], None
    for in_market, daily_return in zip(positions, returns):
        if in_market:
            current = (1 if current is None else current) * (1 + daily_return)
        elif current is not None:
            trades.append(current - 1)
            current = None
    if current is not None:
        trades.append(current - 1)
    return trades


def performance(positions, returns):
    curve = equity_curve(positions, returns)
    trades = trade_returns(positions, returns)
    wins = sum(1 for trade in trades if trade > 0)
    return Performance(
        trade_count=len(trades),
        win_rate=wins / len(trades) * 100 if trades else None,
        total_profit_pct=((curve[-1] if curve else 1.0) - 1) * 100,
        max_drawdown_pct=max_drawdown_pct(curve),
        days_in_market=sum(1 for p in positions if p),
    )
