"""Step 10: try thresholds for the combining rule and keep the best on the backtest."""

from dataclasses import dataclass

from apps.backtest import metrics
from apps.backtest.models import BacktestRun
from apps.backtest.services.backtest_service import Market, combined_positions

# 50 means "no edge", so a buy needs at least 55.
THRESHOLDS = [55, 60, 65, 70, 75, 80]
AGENTS_REQUIRED = [3, 2]
# Fewer trades than this is too little evidence to pick a rule on.
MIN_TRADES = 3
DEFAULT_RULE = {"threshold": 60, "agents_required": 3}


@dataclass
class Candidate:
    threshold: int
    agents_required: int
    performance: metrics.Performance
    first_half_pct: float
    second_half_pct: float


def split(market):
    middle = len(market.days) // 2
    return (
        Market(market.days[:middle], market.next_day_returns[:middle], market.closes),
        Market(market.days[middle:], market.next_day_returns[middle:], market.closes),
    )


def evaluate_candidate(scores_by_day, market, threshold, agents_required):
    def profit(part):
        positions = combined_positions(scores_by_day, part.days, threshold, agents_required)
        return metrics.performance(positions, part.next_day_returns)

    first, second = split(market)
    return Candidate(threshold, agents_required, profit(market),
                     profit(first).total_profit_pct, profit(second).total_profit_pct)


def sweep(scores_by_day, market):
    return [evaluate_candidate(scores_by_day, market, threshold, required)
            for required in AGENTS_REQUIRED for threshold in THRESHOLDS]


def best(candidates):
    """Highest total profit among candidates with enough trades; ties go to lower drawdown."""
    eligible = [c for c in candidates if c.performance.trade_count >= MIN_TRADES]
    if not eligible:
        return None
    return max(eligible, key=lambda c: (round(c.performance.total_profit_pct, 6), -c.performance.max_drawdown_pct))


def choose(score_type, scores_by_day, market, save=True):
    """Sweep, pick, and store the chosen rule. Returns (candidates, chosen or None)."""
    candidates = sweep(scores_by_day, market)
    chosen = best(candidates)
    if save and chosen:
        hold = metrics.performance([True] * len(market.days), market.next_day_returns)
        BacktestRun.objects.create(
            name=f"{score_type}:combining_rule",
            start_date=market.days[0],
            end_date=market.days[-1],
            settings={
                "score_type": score_type,
                "threshold": chosen.threshold,
                "agents_required": chosen.agents_required,
                "first_half_pct": chosen.first_half_pct,
                "second_half_pct": chosen.second_half_pct,
                "days_in_market": chosen.performance.days_in_market,
                "candidates": [
                    {"threshold": c.threshold, "agents_required": c.agents_required,
                     "trades": c.performance.trade_count, "profit_pct": c.performance.total_profit_pct}
                    for c in candidates
                ],
            },
            trade_count=chosen.performance.trade_count,
            win_rate=chosen.performance.win_rate,
            total_profit_pct=chosen.performance.total_profit_pct,
            max_drawdown_pct=chosen.performance.max_drawdown_pct,
            buy_and_hold_pct=hold.total_profit_pct,
        )
    return candidates, chosen


def current_rule():
    """The most recently chosen rule (Opus-tuned preferred), or the plan's starting default."""
    for score_type in ("opus", "rules"):
        run = BacktestRun.objects.filter(name=f"{score_type}:combining_rule").order_by("-created_at").first()
        if run:
            return {"score_type": score_type, "threshold": run.settings["threshold"],
                    "agents_required": run.settings["agents_required"]}
    return {"score_type": "opus", **DEFAULT_RULE}
