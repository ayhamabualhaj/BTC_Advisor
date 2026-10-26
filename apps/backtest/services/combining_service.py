"""Chooses the two-round vote's group lead on one period, then tests it once on a later one.

The choice is made on 2019-2024 only; 2025 onward is the test, reported but never used
to choose. Candidates and the way to pick are fixed here, before looking at the test:
the highest 7-day hit rate of the vote's Buy and Sell calls, among candidates with at
least MIN_CALLS calls (ties: more calls).

Opus has no scores before mid-2026, so the choice is made on the Rules and ML votes
agreeing; live, the Opus vote must agree too.
"""

import datetime
from dataclasses import asdict, dataclass

from apps.backtest import metrics
from apps.backtest.decision_rule import decide
from apps.backtest.models import BacktestRun

TUNE_START = datetime.date(2019, 1, 1)
TUNE_END = datetime.date(2024, 12, 31)
TEST_START = datetime.date(2025, 1, 1)
GROUP_LEADS = [1, 2, 3]
MIN_CALLS = 100
# Round 2 is fixed: every group vote must agree. Stored with the rule so a choice saved
# under an older round 2 is not reused.
OVERALL = "all agree"
DEFAULT_RULE = {"group_lead": 1, "overall": OVERALL}
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
    group_lead: int
    tuning: Result
    test: Result

    @property
    def rule(self):
        return {"group_lead": self.group_lead, "overall": OVERALL}


def evaluate(rule, scores_by_source, days, next_day_returns, returns_7d):
    """Hit rate of the overall vote's calls over 7 days, and profit when buying only on Buy days."""
    right = wrong = 0
    positions = []
    for day in days:
        _, signal = decide({source: scores.get(day, {}) for source, scores in scores_by_source.items()}, rule)
        positions.append(signal == "buy")
        move = returns_7d.get(day)
        if signal in ("buy", "sell") and move:
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
    found = []
    for group_lead in GROUP_LEADS:
        rule = {"group_lead": group_lead, "overall": OVERALL}
        found.append(Candidate(group_lead, evaluate(rule, scores_by_source, *tune, returns_7d),
                               evaluate(rule, scores_by_source, *test, returns_7d)))
    return found


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
        record = chosen or next(c for c in found if c.rule == DEFAULT_RULE)
        BacktestRun.objects.create(
            name=RULE_NAME,
            # The stored numbers are the test period's: the honest ones.
            start_date=TEST_START,
            end_date=test_end,
            settings={
                **record.rule,
                "is_default": chosen is None,
                "tuned_on": [TUNE_START.isoformat(), TUNE_END.isoformat()],
                "tuning": asdict(record.tuning),
                "test": asdict(record.test),
                "candidates": [{**c.rule, "tuning": asdict(c.tuning), "test": asdict(c.test)} for c in found],
            },
            trade_count=record.test.trades,
            win_rate=record.test.hit_rate,
            total_profit_pct=record.test.profit_pct,
            max_drawdown_pct=record.test.drawdown_pct,
            buy_and_hold_pct=record.test.hold_pct,
        )
    return found, chosen


def current_rule():
    """The latest chosen vote, or the default (group lead 1)."""
    run = BacktestRun.objects.filter(name=RULE_NAME).order_by("-created_at").first()
    # Choices saved under an older vote do not apply to this one.
    if run is None or run.settings.get("overall") != OVERALL:
        return dict(DEFAULT_RULE)
    return {"group_lead": run.settings["group_lead"], "overall": OVERALL}


def describe(rule):
    if "group_lead" not in rule:  # a Decision or BacktestRun from the one-round vote
        who = " + ".join({"rules": "rules", "ml": "ML", "opus": "Opus"}[s] for s in rule.get("sources", []))
        return f"one-round vote of the {who} agents, Buy when Buy votes lead by {rule.get('min_net_votes')}+"
    if "overall_lead" in rule:  # the first two-round vote
        return (f"the Rules, ML and Opus agents each vote among their 3 domains (Buy when Buy leads by "
                f"{rule['group_lead']}+), then those 3 votes vote (Buy when Buy leads by {rule['overall_lead']}+)")
    return (f"the Rules, ML and LLM agents each vote among their domains (3 rules; ML: macro and financial "
            f"stress; 3 LLM; Buy when Buy leads by {rule['group_lead']}+); the overall vote calls only when "
            f"all those votes agree")
