import datetime

from django.test import SimpleTestCase, TestCase

from apps.data.collectors.base import Point
from apps.data.indicators import levels, macro, momentum, trend
from apps.data.repositories import market_data_repository
from apps.data.services import indicator_service

# Wilder's worked example from StockCharts. They round the averages along the way and
# publish 70.53 and 66.32; without rounding the values are 70.46 and 66.25.
WILDER_CLOSES = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
                 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]


class TrendTests(SimpleTestCase):
    def test_sma_uses_last_values(self):
        self.assertEqual(trend.sma([1, 2, 3, 4], 2), 3.5)

    def test_sma_with_too_little_data_is_none(self):
        self.assertIsNone(trend.sma([1, 2], 3))

    def test_ema_seeds_with_sma_then_smooths(self):
        result = trend.ema_series([1, 2, 3, 4], 3)
        self.assertEqual(result[:3], [None, None, 2.0])
        self.assertAlmostEqual(result[3], 0.5 * 4 + 0.5 * 2)

    def test_pct_change(self):
        self.assertAlmostEqual(trend.pct_change([100, 105, 110], 2), 10.0)
        self.assertIsNone(trend.pct_change([100], 1))

    def test_rolling_sum(self):
        self.assertEqual(trend.rolling_sum([5, -2, 3], 2), 1)


    def test_volatility_of_daily_moves(self):
        # Daily moves of +10% and -10% alternate: standard deviation 10.
        self.assertAlmostEqual(trend.volatility([100, 110, 99, 108.9, 98.01], 4), 10.0)
        self.assertIsNone(trend.volatility([100, 101], 2))


class MomentumTests(SimpleTestCase):
    def test_rsi_matches_wilders_example(self):
        self.assertAlmostEqual(momentum.rsi(WILDER_CLOSES), 70.53, delta=0.1)
        self.assertAlmostEqual(momentum.rsi(WILDER_CLOSES + [46.00]), 66.32, delta=0.1)

    def test_rsi_extremes(self):
        self.assertEqual(momentum.rsi(list(range(1, 20))), 100.0)
        self.assertEqual(momentum.rsi(list(range(20, 1, -1))), 0.0)
        self.assertIsNone(momentum.rsi([1, 2, 3]))

    def test_macd_of_flat_prices_is_zero(self):
        macd, signal = momentum.macd_series([100.0] * 40)
        self.assertEqual((macd[-1], signal[-1]), (0.0, 0.0))
        self.assertIsNone(macd[24])
        self.assertIsNone(signal[32])
        self.assertIsNotNone(signal[33])

    # Accelerating trends keep MACD clearly on one side of its signal line until the turn.
    def crosses_after_turn(self, closes):
        return [momentum.macd_cross(closes[:n]) for n in range(41, len(closes) + 1)]

    def test_bullish_cross_after_downtrend_turns_up(self):
        down = [100 - 0.05 * i * i for i in range(40)]
        crosses = self.crosses_after_turn(down + [down[-1] + 2 * i for i in range(1, 15)])
        # The cross is reported for three days, then it is too old.
        self.assertEqual(crosses.count("bullish"), 3)
        self.assertNotIn("bearish", crosses)

    def test_bearish_cross_after_uptrend_turns_down(self):
        up = [60 + 0.05 * i * i for i in range(40)]
        crosses = self.crosses_after_turn(up + [up[-1] - 2 * i for i in range(1, 15)])
        self.assertEqual(crosses.count("bearish"), 3)
        self.assertNotIn("bullish", crosses)

    def test_no_cross_in_steady_trend(self):
        self.assertIsNone(momentum.macd_cross([float(i) for i in range(1, 80)]))


class LevelTests(SimpleTestCase):
    def test_swing_points(self):
        lows = [5, 4, 3, 2, 3, 4, 5]
        self.assertEqual(levels.swing_points(lows, 2, is_high=False), [2])

    def test_near_support(self):
        lows = [110, 105, 100, 105, 110, 108, 106]
        highs = [low + 5 for low in lows]
        result = levels.support_resistance(highs, lows, close=102, window=2)
        self.assertEqual(result["support"], 100)
        self.assertTrue(result["near_support"])
        # The swing high of 115 is about 13% away: a resistance, but not near.
        self.assertEqual(result["resistance"], 115)
        self.assertFalse(result["near_resistance"])

    def test_far_from_levels(self):
        lows = [110, 105, 50, 105, 110, 108, 106]
        result = levels.support_resistance([low + 5 for low in lows], lows, close=102, window=2)
        self.assertFalse(result["near_support"])


class MacroTests(SimpleTestCase):
    def test_last_rate_change(self):
        self.assertEqual(macro.last_rate_change([4.5, 4.5, 4.25, 4.25], 5), -1)
        self.assertEqual(macro.last_rate_change([4.25, 4.5, 4.5], 5), 1)
        self.assertEqual(macro.last_rate_change([4.25, 4.5, 4.5, 4.5], 1), 0)

    def test_cuts_expected(self):
        self.assertTrue(macro.cuts_expected(3.6, 4.33))
        self.assertFalse(macro.cuts_expected(4.2, 4.33))
        self.assertIsNone(macro.cuts_expected(None, 4.33))

    def test_cpi_surprise_compares_with_recent_trend(self):
        # Three months of +1% then +0.5%: half a point cooler than the trend.
        cpi = [100, 101, 102.01, 103.0301, 103.0301 * 1.005]
        self.assertAlmostEqual(macro.cpi_surprise(cpi), -0.5, places=6)

    def test_yoy_inflation(self):
        self.assertAlmostEqual(macro.yoy_inflation([100] + [101] * 11 + [103]), 3.0)
        self.assertIsNone(macro.yoy_inflation([100] * 12))


class SnapshotTests(TestCase):
    START = datetime.date(2026, 1, 1)

    def save_daily(self, source, field, values):
        points = [Point(self.START + datetime.timedelta(days=i), field, v) for i, v in enumerate(values)]
        market_data_repository.save_points(source, points)

    def test_snapshot_never_uses_data_after_the_decision_date(self):
        self.save_daily("binance", "close", [100.0] * 30 + [1_000_000.0])
        self.save_daily("binance", "high", [101.0] * 31)
        self.save_daily("binance", "low", [99.0] * 31)
        decision_date = self.START + datetime.timedelta(days=29)
        snapshot = indicator_service.technical_snapshot(decision_date)
        self.assertEqual(snapshot["close"], 100.0)
        self.assertEqual(snapshot["change_7d_pct"], 0.0)

    def test_missing_long_history_gives_none(self):
        self.save_daily("binance", "close", [100.0] * 30)
        snapshot = indicator_service.technical_snapshot(self.START + datetime.timedelta(days=29))
        self.assertIsNone(snapshot["sma_200"])
        self.assertEqual(snapshot["sma_50"], None)
        self.assertEqual(snapshot["sma_20"], 100.0)
        self.assertEqual(snapshot["volatility_14d_pct"], 0.0)

    def test_stale_series_is_ignored(self):
        self.save_daily("bybit", "funding_rate", [0.0001] * 7)
        later = self.START + datetime.timedelta(days=30)
        self.assertIsNone(indicator_service.derivatives_snapshot(later)["funding_rate"])

    def test_no_data_at_all(self):
        self.assertEqual(indicator_service.technical_snapshot(self.START), {"close": None})
        self.assertIsNone(indicator_service.macro_snapshot(self.START)["dxy_change_2w_pct"])
