import datetime
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from apps.backtest import metrics
from apps.backtest.decision_rule import agents_above, is_buy
from apps.backtest.models import BacktestRun
from apps.agents.models import AgentRun
from apps.backtest.services import backtest_service, opus_backtest_service, score_history
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository

D0 = datetime.date(2026, 7, 1)


def day(n):
    return D0 + datetime.timedelta(days=n)


class MetricsTests(SimpleTestCase):
    def test_equity_only_moves_when_in_market(self):
        self.assertEqual(metrics.equity_curve([True, False, True], [0.1, 0.5, -0.1]),
                         [1.1, 1.1, 1.1 * 0.9])

    def test_max_drawdown(self):
        self.assertAlmostEqual(metrics.max_drawdown_pct([1.0, 1.2, 0.9, 1.3, 1.04]), 25.0)
        self.assertEqual(metrics.max_drawdown_pct([1.0, 1.1, 1.2]), 0.0)

    def test_consecutive_days_form_one_trade(self):
        trades = metrics.trade_returns([True, True, False, True], [0.1, 0.1, 0.3, -0.05])
        self.assertEqual(len(trades), 2)
        self.assertAlmostEqual(trades[0], 0.21)
        self.assertAlmostEqual(trades[1], -0.05)

    def test_performance(self):
        result = metrics.performance([True, False, True, True], [0.1, -0.2, -0.1, 0.05])
        self.assertEqual((result.trade_count, result.win_rate, result.days_in_market), (2, 50.0, 3))
        self.assertAlmostEqual(result.total_profit_pct, (1.1 * 0.9 * 1.05 - 1) * 100)

    def test_never_in_market(self):
        result = metrics.performance([False, False], [0.1, 0.1])
        self.assertEqual((result.trade_count, result.win_rate, result.total_profit_pct), (0, None, 0.0))


class DecisionRuleTests(SimpleTestCase):
    def test_counts_agents_at_or_above_threshold(self):
        self.assertEqual(agents_above({"a": 60, "b": 59, "c": None}, 60), 1)

    def test_all_three_or_two(self):
        scores = {"technical": 70, "derivatives": 65, "macro": 50}
        self.assertFalse(is_buy(scores, 60, 3))
        self.assertTrue(is_buy(scores, 60, 2))


class BacktestServiceTests(TestCase):
    def setUp(self):
        # Price goes 100, 110, 99, 99, 108.9: up 10%, down 10%, flat, up 10%.
        closes = [100.0, 110.0, 99.0, 99.0, 108.9]
        market_data_repository.save_points("binance", [Point(day(i), "close", c) for i, c in enumerate(closes)])

    def test_last_day_without_next_price_is_left_out(self):
        market = backtest_service.load_market(day(0), day(4))
        self.assertEqual(market.days, [day(0), day(1), day(2), day(3)])
        self.assertAlmostEqual(market.next_day_returns[1], -0.1)

    def test_agents_alone_and_combined(self):
        market = backtest_service.load_market(day(0), day(4))
        scores = {
            day(0): {"technical": 70, "macro": 70},  # both buy, +10%
            day(1): {"technical": 70, "macro": 40},  # technical alone buys, -10%
            day(2): {"technical": 40, "macro": 40},
            day(3): {"technical": 40, "macro": 80},  # macro alone buys, +10%
        }
        runs = backtest_service.run_backtest("rules", scores, market, threshold=60, agents_required=2)
        by_name = {run.name: run for run in runs}

        self.assertAlmostEqual(by_name["rules:technical"].total_profit_pct, (1.1 * 0.9 - 1) * 100)
        self.assertEqual(by_name["rules:technical"].trade_count, 1)
        self.assertAlmostEqual(by_name["rules:macro"].total_profit_pct, (1.1 * 1.1 - 1) * 100)
        self.assertEqual(by_name["rules:macro"].win_rate, 100.0)
        self.assertAlmostEqual(by_name["rules:combined"].total_profit_pct, 10.0)
        self.assertAlmostEqual(by_name["rules:combined"].buy_and_hold_pct, 8.9)
        self.assertEqual(BacktestRun.objects.count(), 3)

    def test_missing_score_means_no_buy(self):
        market = backtest_service.load_market(day(0), day(4))
        scores = {d: {"technical": None} for d in market.days}
        [alone, combined] = backtest_service.run_backtest("rules", scores, market, save=False)
        self.assertEqual((alone.trade_count, combined.trade_count), (0, 0))
        self.assertEqual(BacktestRun.objects.count(), 0)


class OpusBacktestTests(TestCase):
    def setUp(self):
        start = day(0) - datetime.timedelta(days=30)
        closes = [Point(start + datetime.timedelta(days=i), field, 100.0 + i)
                  for i in range(36) for field in ("close", "high", "low")]
        market_data_repository.save_points("binance", closes)
        self.days = [day(0), day(1), day(2)]

    def test_runs_each_day_once_and_resumes(self):
        from tests.fake_anthropic import FakeClient

        client = FakeClient()
        progress = opus_backtest_service.run(["technical"], self.days, Decimal("10"), client)
        self.assertEqual((progress.calls, progress.stopped_at_cap), (3, False))
        self.assertEqual(AgentRun.objects.filter(is_backtest=True).count(), 3)

        again = opus_backtest_service.run(["technical"], self.days, Decimal("10"), client)
        self.assertEqual(again.calls, 0)
        self.assertEqual(len(client.calls), 3)

    def test_stops_before_passing_the_cost_cap(self):
        from tests.fake_anthropic import FakeClient, response

        # Each fake call costs 1000 x $4/M + 500 x $20/M = $0.014; the first estimate is $0.016.
        client = FakeClient(response())
        # After two calls: $0.028 spent + $0.014 expected next > $0.04 cap.
        progress = opus_backtest_service.run(["technical"], self.days, Decimal("0.04"), client)
        self.assertEqual((progress.calls, progress.stopped_at_cap), (2, True))

    def test_estimate_counts_pending_calls(self):
        calls, cost = opus_backtest_service.estimate(["technical", "macro"], self.days)
        self.assertEqual(calls, 6)
        self.assertEqual(cost, 6 * opus_backtest_service.DEFAULT_COST_PER_CALL)

    def test_opus_scores_feed_the_backtest(self):
        from tests.fake_anthropic import FakeClient

        opus_backtest_service.run(["technical"], self.days, Decimal("10"), FakeClient())
        versions = opus_backtest_service.prompt_versions(["technical"])
        scores = score_history.opus_scores(self.days, versions)
        self.assertEqual(scores[day(1)], {"technical": 62})
