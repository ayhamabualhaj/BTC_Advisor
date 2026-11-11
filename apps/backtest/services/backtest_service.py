import datetime
from dataclasses import dataclass

from apps.backtest import metrics
from apps.backtest.decision_rule import is_buy
from apps.backtest.models import BacktestRun
from apps.backtest.repositories import price_repository
from apps.data import assets

DEFAULT_THRESHOLD = 60


@dataclass
class Market:
    """Decision days and the return of holding from each day's close to the next."""
    days: list
    next_day_returns: list
    closes: dict


def load_market(start, end):
    """Each day with a close and the next close after it: the next day for Bitcoin, the next
    session for gold (a Friday's return runs to Monday)."""
    wait = assets.current().outcome_wait_days
    closes = price_repository.closes(start, end + datetime.timedelta(days=1 + wait))
    days, returns = [], []
    for day in sorted(day for day in closes if day <= end):
        following = next((closes[day + datetime.timedelta(days=1 + extra)] for extra in range(wait + 1)
                          if day + datetime.timedelta(days=1 + extra) in closes), None)
        # Only days whose outcome is known can be tested.
        if following is not None:
            days.append(day)
            returns.append(following / closes[day] - 1)
    return Market(days, returns, closes)


def agent_positions(scores_by_day, days, agent, threshold):
    """Alone, an agent buys when its score is at or above the threshold."""
    return [(scores_by_day[day].get(agent) or 0) >= threshold for day in days]


def combined_positions(scores_by_day, days, min_net_votes):
    return [is_buy(scores_by_day[day], min_net_votes) for day in days]


def evaluate(name, market, positions, settings, save=True):
    """Measure one set of positions against buy-and-hold and optionally store a BacktestRun."""
    result = metrics.performance(positions, market.next_day_returns)
    hold = metrics.performance([True] * len(market.days), market.next_day_returns)
    after_fees = metrics.performance(positions, market.next_day_returns, metrics.FEE_PER_SIDE)
    hold_after_fees = metrics.performance([True] * len(market.days), market.next_day_returns, metrics.FEE_PER_SIDE)
    run = BacktestRun(
        name=name,
        start_date=market.days[0],
        end_date=market.days[-1],
        # The model's columns are before fees (as older runs were); the after-fee numbers sit beside them.
        settings={**settings, "days_in_market": result.days_in_market,
                  "buy_and_hold_drawdown_pct": round(hold.max_drawdown_pct, 2),
                  "fee_per_side_pct": metrics.FEE_PER_SIDE * 100,
                  "profit_after_fees_pct": round(after_fees.total_profit_pct, 2),
                  "buy_and_hold_after_fees_pct": round(hold_after_fees.total_profit_pct, 2)},
        trade_count=result.trade_count,
        win_rate=result.win_rate,
        total_profit_pct=result.total_profit_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        buy_and_hold_pct=hold.total_profit_pct,
    )
    if save:
        run.save()
    return run


def run_backtest(score_type, scores_by_day, market, threshold=DEFAULT_THRESHOLD, min_net_votes=1, save=True):
    """One run per agent alone, plus the combined rule. Returns the BacktestRuns."""
    agents = sorted({agent for scores in scores_by_day.values() for agent in scores})
    runs = []
    for agent in agents:
        positions = agent_positions(scores_by_day, market.days, agent, threshold)
        runs.append(evaluate(f"{score_type}:{agent}", market, positions,
                             {"score_type": score_type, "agent": agent, "threshold": threshold}, save))
    positions = combined_positions(scores_by_day, market.days, min_net_votes)
    runs.append(evaluate(f"{score_type}:combined", market, positions,
                         {"score_type": score_type, "min_net_votes": min_net_votes}, save))
    return runs

