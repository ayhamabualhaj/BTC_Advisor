import datetime

from django.test import SimpleTestCase, TestCase

from apps.agents.derivatives import rules as derivatives_rules
from apps.agents.macro import rules as macro_rules
from apps.agents.models import AgentRun
from apps.agents.scoring import RuleScore
from apps.agents.services import rule_scoring_service
from apps.agents.technical import rules as technical_rules
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository


class RuleScoreTests(SimpleTestCase):
    def test_starts_at_fifty(self):
        self.assertEqual(RuleScore().score, 50)
        self.assertEqual(RuleScore().direction, "neutral")

    def test_is_capped_between_0_and_100(self):
        high, low = RuleScore(), RuleScore()
        for _ in range(8):
            high.add("up", 10)
            low.add("down", -10)
        self.assertEqual((high.score, low.score), (100, 0))

    def test_direction_and_reasons(self):
        result = RuleScore()
        result.add("Price above 50-day average", 10)
        self.assertEqual(result.direction, "bullish")
        self.assertEqual(result.reasons, ["Price above 50-day average (+10)"])


class TechnicalRuleTests(SimpleTestCase):
    def test_sharp_drop_into_support_is_bullish(self):
        snapshot = {"close": 90, "sma_20": 100, "sma_200": 80, "rsi_14": 25, "change_7d_pct": -8,
                    "near_support": True, "near_resistance": False}
        self.assertEqual(technical_rules.score(snapshot).score, 50 + 3 + 5 + 3 + 5 + 3)

    def test_stretched_rally_into_resistance_is_bearish(self):
        snapshot = {"close": 110, "sma_20": 100, "sma_200": 120, "rsi_14": 75, "change_7d_pct": 8,
                    "near_support": False, "near_resistance": True}
        self.assertEqual(technical_rules.score(snapshot).score, 50 - 3 - 5 - 5 - 5 - 3)

    def test_an_uptrend_alone_is_barely_bullish(self):
        # Above every average with normal momentum: the trend is context, not a buy signal.
        result = technical_rules.score({"close": 100, "sma_20": 98, "sma_50": 95, "sma_200": 80,
                                        "rsi_14": 60, "change_7d_pct": 2, "macd_cross_3d": "bullish"})
        self.assertEqual((result.score, result.direction), (53, "neutral"))

    def test_missing_data_is_skipped_not_counted(self):
        result = technical_rules.score({"close": None})
        self.assertEqual(result.score, 50)
        self.assertEqual(result.skipped, ["200-day average", "20-day average", "7-day change", "RSI"])


class DerivativesRuleTests(SimpleTestCase):
    def test_very_high_funding_is_bearish(self):
        self.assertEqual(derivatives_rules.score({"funding_rate": 0.0005}).score, 45)

    def test_negative_funding_and_a_flush_are_bullish(self):
        snapshot = {"funding_rate": -0.0001, "long_liquidations_usd_1d": 30_000_000}
        self.assertEqual(derivatives_rules.score(snapshot).score, 50 + 5 + 5)

    def test_open_interest_and_crowd_no_longer_move_the_score(self):
        # Both failed on the tuning period: OI rising into a falling price was not bearish
        # and fading an extreme crowd pointed the wrong way.
        snapshot = {"funding_rate": 0.0001, "open_interest_change_3d_pct": 5, "price_change_3d_pct": -2,
                    "long_liquidations_usd_1d": 1_000_000,
                    "long_account_ratio": 0.72, "long_account_ratio_90d_avg": 0.60}
        result = derivatives_rules.score(snapshot)
        self.assertEqual((result.score, result.skipped), (50, []))

    def test_missing_data_is_skipped(self):
        self.assertEqual(derivatives_rules.score({}).skipped, ["Funding rate", "Liquidations"])


class MacroRuleTests(SimpleTestCase):
    def test_supportive_macro(self):
        snapshot = {"dxy_change_2w_pct": -1.2, "nasdaq": 110, "nasdaq_sma_50": 100,
                    "fed_rate_change_60d": -1, "cpi_surprise_pct": -0.1, "etf_net_flow_5d_musd": 500}
        self.assertEqual(macro_rules.score(snapshot).score, 50 + 10 + 10 + 10 + 5 + 10)

    def test_hostile_macro(self):
        snapshot = {"dxy_change_2w_pct": 1.2, "nasdaq": 90, "nasdaq_sma_50": 100,
                    "fed_rate_change_60d": 1, "cuts_expected": True,
                    "cpi_surprise_pct": 0.1, "etf_net_flow_5d_musd": -500}
        # A hike outweighs cut expectations.
        self.assertEqual(macro_rules.score(snapshot).score, 50 - 10 - 10 - 15 - 5 - 10)

    def test_expected_cuts_count_like_a_cut(self):
        result = macro_rules.score({"fed_rate_change_60d": 0, "cuts_expected": True})
        self.assertEqual(result.score, 60)

    def test_small_dollar_move_is_flat(self):
        self.assertEqual(macro_rules.score({"dxy_change_2w_pct": 0.3}).score, 50)


class RuleScoringServiceTests(TestCase):
    def test_save_creates_one_rule_only_run_per_agent(self):
        start = datetime.date(2026, 1, 1)
        closes = [Point(start + datetime.timedelta(days=i), "close", 100.0 + i) for i in range(60)]
        market_data_repository.save_points("binance", closes)
        date = start + datetime.timedelta(days=59)

        results = rule_scoring_service.run_rules(date, save=True)

        self.assertEqual(set(results), {"technical", "derivatives", "macro"})
        run = AgentRun.objects.get(agent="technical")
        # A steady climb: 6.4% above the 20-day average (-5) and RSI 100 (-5); the 7-day
        # gain of 4.6% is under the cutoff and 60 days are too few for the 200-day average.
        self.assertEqual(run.rule_score, 40)
        self.assertEqual(run.reasons, ["Price 6.4% above 20-day average: stretched (-5)",
                                       "RSI 100: overbought (-5)"])
        self.assertIsNone(run.opus_score)
        self.assertIn("200-day average", run.key_data["skipped"])
        self.assertEqual(AgentRun.objects.count(), 3)
