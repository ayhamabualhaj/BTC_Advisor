"""The dollar domain: its math, its snapshot and its ML-only agent, which votes only in the strong signal."""

import datetime

from django.test import SimpleTestCase, TestCase

from ai import dollar
from ai.domains import has, with_kind
from apps.backtest.decision_rule import STRONG_ONLY, STRONG_VOTERS, VOTERS_ROUND_2
from apps.data.collectors.base import Point
from apps.data.indicators import relative
from apps.data.repositories import market_data_repository
from apps.data.services import indicator_service

DAY = datetime.date(2026, 3, 6)  # a Friday


class RelativeMathTests(SimpleTestCase):
    def test_returns_and_correlation(self):
        self.assertEqual(relative.returns([100, 110, 99]), [0.10000000000000009, -0.09999999999999998])
        self.assertAlmostEqual(relative.correlation([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertAlmostEqual(relative.correlation([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertIsNone(relative.correlation([1, 1, 1], [1, 2, 3]))  # one side never moves
        self.assertIsNone(relative.correlation([1, 2], [1, 2, 3]))


class DollarDomainTests(SimpleTestCase):
    def test_dollar_has_only_an_ml_agent_and_votes_only_in_the_strong_signal(self):
        self.assertTrue(has("dollar", "ml"))
        self.assertFalse(has("dollar", "rules"))
        self.assertFalse(has("dollar", "opus"))
        self.assertIn("dollar", with_kind("ml"))
        self.assertEqual(STRONG_ONLY, {"dollar": ("ml", "dollar")})
        self.assertNotIn("dollar", VOTERS_ROUND_2)
        self.assertEqual(STRONG_VOTERS, VOTERS_ROUND_2 + ["dollar"])


class DollarSnapshotTests(TestCase):
    def setUp(self):
        # 100 calendar days; the index trades on weekdays only and rises 0.1 a session, Bitcoin 1 a day.
        days = [DAY - datetime.timedelta(days=i) for i in range(100)]
        weekdays = sorted(day for day in days if day.weekday() < 5)
        market_data_repository.save_points("yahoo", [Point(day, "dxy_close", 100.0 + 0.1 * i) for i, day in enumerate(weekdays)])
        market_data_repository.save_points("binance", [Point(day, "close", 1000.0 - i) for i, day in enumerate(days)])
        self.last_dxy = 100.0 + 0.1 * (len(weekdays) - 1)

    def test_snapshot_compares_bitcoin_with_the_dollar_on_the_dollars_trading_days(self):
        snapshot = indicator_service.dollar_snapshot(DAY)
        self.assertAlmostEqual(snapshot["dxy_change_5d_pct"], (self.last_dxy / (self.last_dxy - 0.5) - 1) * 100, places=3)
        self.assertAlmostEqual(snapshot["dxy_change_20d_pct"], (self.last_dxy / (self.last_dxy - 2.0) - 1) * 100, places=3)
        self.assertGreater(snapshot["dxy_vs_sma_50_pct"], 0)  # a rising index is above its own average
        # 20 sessions back is 28 calendar days: Bitcoin went from 972 to 1000.
        btc_20d = (1000.0 / 972.0 - 1) * 100
        self.assertAlmostEqual(snapshot["btc_minus_dxy_20d_pct"], btc_20d - snapshot["dxy_change_20d_pct"], places=3)
        self.assertIsNotNone(snapshot["btc_dxy_correlation_60d"])
        self.assertEqual(set(dollar.inputs.model_input(snapshot)), set(snapshot))

    def test_the_last_close_stands_over_the_weekend_but_not_for_long(self):
        sunday = DAY + datetime.timedelta(days=2)
        market_data_repository.save_points("binance", [Point(DAY + datetime.timedelta(days=n), "close", 1000.0) for n in (1, 2)])
        self.assertIsNotNone(indicator_service.dollar_snapshot(sunday)["dxy_change_5d_pct"])
        self.assertIsNone(indicator_service.dollar_snapshot(DAY + datetime.timedelta(days=9))["dxy_change_5d_pct"])

    def test_too_little_history_gives_no_numbers(self):
        early = DAY - datetime.timedelta(days=60)
        self.assertEqual(set(indicator_service.dollar_snapshot(early).values()), {None})
