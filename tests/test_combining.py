import datetime

from django.test import TestCase

from apps.agents.models import AgentRun
from apps.backtest import metrics
from apps.backtest.models import BacktestRun, Decision
from apps.backtest.services import backtest_service, combining_service, decision_service
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository

D0 = datetime.date(2026, 7, 1)


def day(n):
    return D0 + datetime.timedelta(days=n)


def candidate(threshold, trades, profit, drawdown):
    performance = metrics.Performance(trades, 50.0, profit, drawdown, trades)
    return combining_service.Candidate(threshold, 3, performance, 0.0, 0.0)


class BestRuleTests(TestCase):
    def test_needs_enough_trades(self):
        lucky = candidate(70, trades=1, profit=20, drawdown=0)
        steady = candidate(60, trades=5, profit=8, drawdown=3)
        self.assertIs(combining_service.best([lucky, steady]), steady)

    def test_tie_goes_to_lower_drawdown(self):
        risky = candidate(55, trades=5, profit=8, drawdown=9)
        calm = candidate(65, trades=4, profit=8, drawdown=2)
        self.assertIs(combining_service.best([risky, calm]), calm)

    def test_none_when_no_rule_trades_enough(self):
        self.assertIsNone(combining_service.best([candidate(80, trades=0, profit=0, drawdown=0)]))


class ChooseAndDecideTests(TestCase):
    def setUp(self):
        closes = [100.0, 105, 100, 105, 100, 105, 100, 105, 100]
        market_data_repository.save_points("binance", [Point(day(i), "close", c) for i, c in enumerate(closes)])
        self.market = backtest_service.load_market(day(0), day(8))
        # Two agents are confident (70) exactly on the days before a rise; macro never is.
        self.scores = {d: {"technical": 70 if i % 2 == 0 else 40, "derivatives": 70 if i % 2 == 0 else 40,
                           "macro": 40} for i, d in enumerate(self.market.days)}

    def test_sweep_picks_and_saves_a_rule(self):
        candidates, chosen = combining_service.choose("rules", self.scores, self.market)
        self.assertEqual(len(candidates), 12)
        self.assertEqual((chosen.agents_required, chosen.performance.win_rate), (2, 100.0))
        saved = BacktestRun.objects.get(name="rules:combining_rule")
        self.assertEqual(saved.settings["threshold"], chosen.threshold)
        self.assertEqual(len(saved.settings["candidates"]), 12)

    def test_no_qualifying_rule_stores_the_default_over_an_older_choice(self):
        combining_service.choose("rules", self.scores, self.market)
        quiet = {d: {"technical": 50, "derivatives": 50, "macro": 50} for d in self.market.days}
        _, chosen = combining_service.choose("rules", quiet, self.market)
        self.assertIsNone(chosen)
        self.assertEqual(combining_service.current_rule(),
                         {"score_type": "rules", "threshold": 60, "agents_required": 3})

    def test_current_rule_defaults_and_prefers_opus(self):
        self.assertEqual(combining_service.current_rule(),
                         {"score_type": "opus", "threshold": 60, "agents_required": 3})
        combining_service.choose("rules", self.scores, self.market)
        self.assertEqual(combining_service.current_rule()["score_type"], "rules")

    def test_decision_applies_the_rule_to_live_runs(self):
        for agent, score in (("technical", 72), ("derivatives", 66), ("macro", 40)):
            AgentRun.objects.create(date=day(3), agent=agent, rule_score=50, opus_score=score)
        AgentRun.objects.create(date=day(3), agent="macro", rule_score=50, opus_score=90, is_backtest=True)

        decision = decision_service.make_decision(day(3))  # default rule: all three >= 60

        self.assertEqual(decision.signal, Decision.Signal.NO_TRADE)
        self.assertEqual((decision.technical_score, decision.macro_score), (72, 40))
        BacktestRun.objects.create(name="opus:combining_rule", start_date=day(0), end_date=day(8),
                                   settings={"threshold": 65, "agents_required": 2})
        self.assertEqual(decision_service.make_decision(day(3)).signal, Decision.Signal.BUY)
