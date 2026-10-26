import datetime

from django.test import SimpleTestCase, TestCase

from ai.derivatives import rules as derivatives_rules
from ai.macro import rules as macro_rules
from ai.scoring import RuleScore
from ai.technical import rules as technical_rules
from apps.agents.models import AgentRun
from apps.agents.services import rule_scoring_service
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
    def test_normal_trend_is_a_mild_sell(self):
        snapshot = {"close": 100, "sma_50": 98, "sma_200": 95, "change_30d_pct": 4, "volatility_14d_pct": 2}
        self.assertEqual(technical_rules.score(snapshot).score, 40)

    def test_strong_rally_or_high_volatility_overrides_the_sell(self):
        snapshot = {"close": 100, "sma_50": 98, "sma_200": 95, "change_30d_pct": 20, "volatility_14d_pct": 3.5}
        self.assertEqual(technical_rules.score(snapshot).score, 50 - 10 + 10 + 10)

    def test_deep_downtrend_far_below_200_day_is_a_buy(self):
        snapshot = {"close": 70, "sma_50": 85, "sma_200": 100, "change_30d_pct": -10, "volatility_14d_pct": 2}
        result = technical_rules.score(snapshot)
        self.assertEqual((result.score, result.direction), (60, "bullish"))

    def test_missing_data_is_skipped_not_counted(self):
        result = technical_rules.score({"close": None})
        self.assertEqual(result.score, 50)
        self.assertEqual(result.skipped, ["50- vs 200-day average", "30-day change", "Volatility", "200-day average"])


class DerivativesRuleTests(SimpleTestCase):
    def test_crowded_funding_and_open_interest_collapse_are_bearish(self):
        snapshot = {"funding_rate_30d_avg": 0.00005, "funding_rate_7d_avg": 0.00004,
                    "price_change_3d_pct": -3, "open_interest_change_3d_pct": -12}
        self.assertEqual(derivatives_rules.score(snapshot).score, 30)

    def test_quiet_funding_price_jump_and_flush_are_bullish(self):
        snapshot = {"funding_rate_30d_avg": 0.00002, "funding_rate_7d_avg": 0.000001,
                    "price_change_3d_pct": 7, "open_interest_change_3d_pct": 1,
                    "long_liquidations_usd_1d": 30_000_000}
        self.assertEqual(derivatives_rules.score(snapshot).score, 50 + 10 + 10 + 5)

    def test_normal_market_stays_neutral(self):
        snapshot = {"funding_rate_30d_avg": 0.00002, "funding_rate_7d_avg": 0.00002,
                    "price_change_3d_pct": 1, "open_interest_change_3d_pct": 1, "long_liquidations_usd_1d": 1_000_000}
        result = derivatives_rules.score(snapshot)
        self.assertEqual((result.score, result.skipped), (50, []))

    def test_missing_data_is_skipped(self):
        self.assertEqual(derivatives_rules.score({}).skipped,
                         ["30-day funding", "7-day funding", "3-day price change", "Open interest", "Liquidations"])


class MacroRuleTests(SimpleTestCase):
    def test_stock_selloff_and_low_inflation_are_bullish(self):
        snapshot = {"nasdaq_change_5d_pct": -5, "nasdaq_change_20d_pct": -6,
                    "cpi_yoy_pct": 2.4, "cpi_surprise_pct": -0.1}
        self.assertEqual(macro_rules.score(snapshot).score, 80)

    def test_cpi_no_cooler_than_trend_is_bearish(self):
        snapshot = {"nasdaq_change_5d_pct": 1, "nasdaq_change_20d_pct": 2, "cpi_yoy_pct": 3.1, "cpi_surprise_pct": 0}
        self.assertEqual(macro_rules.score(snapshot).score, 40)

    def test_missing_data_is_skipped(self):
        result = macro_rules.score({})
        self.assertEqual((result.score, len(result.skipped)), (50, 4))


class RuleScoringServiceTests(TestCase):
    def test_save_creates_one_rule_only_run_per_agent(self):
        start = datetime.date(2026, 1, 1)
        closes = [Point(start + datetime.timedelta(days=i), "close", 100.0 + i) for i in range(60)]
        market_data_repository.save_points("binance", closes)
        date = start + datetime.timedelta(days=59)

        results = rule_scoring_service.run_rules(date, save=True)

        self.assertEqual(set(results), {"technical", "derivatives", "macro", "riskon"})
        run = AgentRun.objects.get(agent="technical")
        # A steady climb of 23% in 30 days (+10); 60 days are too few for the 200-day average.
        self.assertEqual(run.rule_score, 60)
        self.assertEqual(run.reasons, ["Up 23% in 30 days: strong momentum (+10)"])
        self.assertIsNone(run.opus_score)
        self.assertIn("200-day average", run.key_data["skipped"])
        self.assertEqual(AgentRun.objects.count(), 4)
