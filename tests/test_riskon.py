"""The risk-on day domain: today's Bitcoin and Nasdaq moves, and its Sell-only rule."""

import datetime

from django.test import SimpleTestCase, TestCase

from ai.domains import has, with_kind
from ai.riskon import rules
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from apps.data.services import indicator_service

MONDAY = datetime.date(2026, 3, 2)
FRIDAY = MONDAY - datetime.timedelta(days=3)


class RiskonRuleTests(SimpleTestCase):
    def test_only_a_rules_agent(self):
        self.assertTrue(has("riskon", "rules"))
        self.assertFalse(has("riskon", "ml"))
        self.assertFalse(has("riskon", "opus"))
        self.assertNotIn("riskon", with_kind("ml"))

    def test_sell_when_bitcoin_and_the_nasdaq_both_rose(self):
        result = rules.score({"btc_change_1d_pct": 2.0, "nasdaq_change_1d_pct": 0.5})
        self.assertEqual((result.score, result.direction), (40, "bearish"))
        self.assertIn("next day is often weaker", result.reasons[0])

    def test_no_call_otherwise(self):
        for btc, nasdaq in ((2.0, -0.5), (-1.0, 0.5), (-1.0, -0.5)):
            self.assertEqual(rules.score({"btc_change_1d_pct": btc, "nasdaq_change_1d_pct": nasdaq}).score, 50)

    def test_no_call_when_the_nasdaq_did_not_trade(self):
        result = rules.score({"btc_change_1d_pct": 2.0, "nasdaq_change_1d_pct": None})
        self.assertEqual((result.score, result.skipped), (50, ["Bitcoin and Nasdaq moves today"]))


class RiskonSnapshotTests(TestCase):
    def setUp(self):
        days = [MONDAY - datetime.timedelta(days=i) for i in range(5)]
        market_data_repository.save_points("binance", [Point(d, "close", 100.0 - i) for i, d in enumerate(days)])
        # The Nasdaq trades on Friday and Monday, not over the weekend.
        market_data_repository.save_points("yahoo", [Point(FRIDAY, "nasdaq_close", 200.0), Point(MONDAY, "nasdaq_close", 202.0)])

    def test_moves_since_the_previous_close(self):
        snapshot = indicator_service.riskon_snapshot(MONDAY)
        self.assertAlmostEqual(snapshot["btc_change_1d_pct"], (100 / 99 - 1) * 100, places=3)
        # Monday's Nasdaq move is from Friday's close.
        self.assertAlmostEqual(snapshot["nasdaq_change_1d_pct"], 1.0, places=3)

    def test_no_nasdaq_move_on_a_day_it_did_not_trade(self):
        snapshot = indicator_service.riskon_snapshot(MONDAY - datetime.timedelta(days=1))  # Sunday
        self.assertIsNone(snapshot["nasdaq_change_1d_pct"])
        self.assertIsNotNone(snapshot["btc_change_1d_pct"])
