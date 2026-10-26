"""Chooses the vote (who votes, and by what margin) on one period, then tests it once on a later one.

The choice is made on 2019-2024 only; 2025 onward is the test, reported but never used
to choose. Candidates and the way to pick are fixed here, before looking at the test:
the highest 7-day hit rate of the vote's Buy and Sell calls, among candidates with at
least MIN_CALLS calls (ties: more calls).
"""

import datetime
from dataclasses import asdict, dataclass

from apps.backtest import metrics
from apps.backtest.decision_rule import call, voters
from apps.backtest.models import BacktestRun

TUNE_START = datetime.date(2019, 1, 1)
TUNE_END = datetime.date(2024, 12, 31)
TEST_START = datetime.date(2025, 1, 1)
SOURCE_SETS = [["rules"], ["rules", "ml"]]
MARGINS = [1, 2, 3]
MIN_CALLS = 100
DEFAULT_RULE = {"sources": ["rules"], "min_net_votes": 1}
RULE_NAME = "combining_rule"


@dataclass
class Result:
    calls: int
    right: int
    hit_rate: float | None
    buy_days: int
    trades: int
    profit_pct: float
    drawdown_pct: float
    hold_pct: float


@dataclass
class Candidate:
    sources: list
    min_net_votes: int
    tuning: Result
    test: Result


def evaluate(sources, margin, scores_by_source, days, next_day_returns, returns_7d):
    """Hit rate of the vote's calls over 7 days, and profit when buying only on Buy days."""
    right = wrong = 0
    positions = []
    for day in days:
        signal = call(voters({source: scores_by_source[source].get(day, {}) for source in sources}, sources), margin)
        positions.append(signal == "buy")
        move = returns_7d.get(day)
        if signal != "hold" and move:
            if (signal == "buy") == (move > 0):
                right += 1
            else:
                wrong += 1
    performance = metrics.performance(positions, next_day_returns)
    hold = metrics.performance([True] * len(days), next_day_returns)
    return Result(right + wrong, right, right / (right + wrong) * 100 if right + wrong else None,
                  performance.days_in_market, performance.trade_count, performance.total_profit_pct,
                  performance.max_drawdown_pct, hold.total_profit_pct)


def split(market, start, end):
    pairs = [(day, ret) for day, ret in zip(market.days, market.next_day_returns) if start <= day <= end]
    return [day for day, _ in pairs], [ret for _, ret in pairs]


def candidates(scores_by_source, market, returns_7d, test_end):
    tune = split(market, TUNE_START, TUNE_END)
    test = split(market, TEST_START, test_end)
    return [
        Candidate(sources, margin,
                  evaluate(sources, margin, scores_by_source, *tune, returns_7d),
                  evaluate(sources, margin, scores_by_source, *test, returns_7d))
        for sources in SOURCE_SETS for margin in MARGINS
    ]


def best(found):
    eligible = [c for c in found if c.tuning.calls >= MIN_CALLS and c.tuning.hit_rate is not None]
    if not eligible:
        return None
    return max(eligible, key=lambda c: (round(c.tuning.hit_rate, 6), c.tuning.calls))


def choose(scores_by_source, market, returns_7d, test_end, save=True):
    """Returns (candidates, chosen or None) and stores the chosen vote (or the default)."""
    found = candidates(scores_by_source, market, returns_7d, test_end)
    chosen = best(found)
    if save:
        record = chosen or next(c for c in found if c.sources == DEFAULT_RULE["sources"]
                                and c.min_net_votes == DEFAULT_RULE["min_net_votes"])
        BacktestRun.objects.create(
            name=RULE_NAME,
            # The stored numbers are the test period's: the honest ones.
            start_date=TEST_START,
            end_date=test_end,
            settings={
                "sources": record.sources,
                "min_net_votes": record.min_net_votes,
                "is_default": chosen is None,
                "tuned_on": [TUNE_START.isoformat(), TUNE_END.isoformat()],
                "tuning": asdict(record.tuning),
                "test": asdict(record.test),
                "candidates": [{"sources": c.sources, "min_net_votes": c.min_net_votes,
                                "tuning": asdict(c.tuning), "test": asdict(c.test)} for c in found],
            },
            trade_count=record.test.trades,
            win_rate=record.test.hit_rate,
            total_profit_pct=record.test.profit_pct,
            max_drawdown_pct=record.test.drawdown_pct,
            buy_and_hold_pct=record.test.hold_pct,
        )
    return found, chosen


def current_rule():
    """The latest chosen vote, or the default: rules only, Buy votes ahead by 1."""
    run = BacktestRun.objects.filter(name=RULE_NAME).order_by("-created_at").first()
    if run is None:
        return dict(DEFAULT_RULE)
    return {"sources": run.settings["sources"], "min_net_votes": run.settings["min_net_votes"]}


def describe(rule):
    who = " + ".join({"rules": "rules", "ml": "ML", "opus": "Opus"}[s] for s in rule["sources"])
    return f"vote of the {who} agents, Buy when Buy votes lead by {rule['min_net_votes']}+"
