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


def months(values):
    """Index values as consecutive monthly observations: [(month number, value)]."""
    return list(enumerate(values))


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
        cpi = months([100, 101, 102.01, 103.0301, 103.0301 * 1.005])
        self.assertAlmostEqual(macro.cpi_surprise(cpi), -0.5, places=6)

    def test_yoy_inflation(self):
        self.assertAlmostEqual(macro.yoy_inflation(months([100] + [101] * 11 + [103])), 3.0)
        self.assertIsNone(macro.yoy_inflation(months([100] * 12)))

    def test_month_number_counts_across_a_year_end(self):
        self.assertEqual(macro.month_number(202601) - macro.month_number(202512), 1)

    def test_a_month_never_published_is_filled_at_the_steady_rate(self):
        # 100 -> 121 over two months is +10% a month, so the missing month is 110.
        filled = macro.every_month([(1, 100), (3, 121), (4, 121)])
        self.assertEqual(len(filled), 4)
        self.assertAlmostEqual(filled[1], 110)

    def test_yoy_inflation_counts_real_months_across_a_missing_one(self):
        # 13 prints with one month missing span 13 months: the year starts at the 2nd print.
        cpi = [(0, 90), (1, 100)] + [(month, 101) for month in range(2, 9)] \
            + [(month, 101) for month in range(10, 13)] + [(13, 103)]
        self.assertEqual(len(cpi), 13)
        self.assertAlmostEqual(macro.yoy_inflation(cpi), 3.0)

    def test_cpi_surprise_reads_a_two_month_print_at_its_monthly_rate(self):
        # +1% a month throughout, the last print covering two months (+2.01%): no surprise.
        cpi = [(0, 100), (1, 101), (2, 102.01), (3, 103.0301), (5, 103.0301 * 1.0201)]
        self.assertAlmostEqual(macro.cpi_surprise(cpi), 0, places=6)

    def test_cpi_surprise_after_a_two_month_print_uses_its_monthly_rate_in_the_trend(self):
        # +1% a month throughout, then a flat month: one point cooler than the trend.
        cpi = [(0, 100), (1, 101), (2, 102.01), (4, 102.01 * 1.0201), (5, 102.01 * 1.0201)]
        self.assertAlmostEqual(macro.cpi_surprise(cpi), -1, places=6)


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

    def save_cpi(self, prints):
        """prints: [(publication day, YYYYMM, value)]."""
        market_data_repository.save_points("fred", [Point(day, "cpi", value) for day, _, value in prints])
        market_data_repository.save_points("fred", [Point(day, "cpi_month", month) for day, month, _ in prints])

    def cpi_prints_without_october_2025(self):
        """Flat at 100 until September 2025 (101), then November 2025 on at 103; each print
        comes out on the 15th of the next month."""
        def published(year, month):
            return datetime.date(year + month // 12, month % 12 + 1, 15)

        early = [(published(2024, m), 202400 + m, 100.0) for m in range(9, 13)] \
            + [(published(2025, m), 202500 + m, 100.0) for m in range(1, 9)] + [(published(2025, 9), 202509, 101.0)]
        late = [(published(2025, 11), 202511, 103.0), (published(2025, 12), 202512, 103.0)] \
            + [(published(2026, m), 202600 + m, 103.0) for m in range(1, 10)]
        return early + late

    def test_inflation_is_measured_over_twelve_real_months_when_one_was_never_published(self):
        self.save_cpi(self.cpi_prints_without_october_2025())
        # The print for September 2026 (103) against September 2025 (101), not August 2025 (100).
        snapshot = indicator_service.macro_snapshot(datetime.date(2026, 10, 20))
        self.assertAlmostEqual(snapshot["cpi_yoy_pct"], (103 / 101 - 1) * 100, places=3)

    def test_cpi_print_published_later_is_not_seen(self):
        self.save_cpi(self.cpi_prints_without_october_2025())
        # The day before November 2025 comes out, September 2025 (101 vs 100) is the latest.
        snapshot = indicator_service.macro_snapshot(datetime.date(2025, 12, 14))
        self.assertAlmostEqual(snapshot["cpi_yoy_pct"], 1.0, places=3)

    def test_cpi_without_its_month_is_left_out(self):
        prints = self.cpi_prints_without_october_2025()
        market_data_repository.save_points("fred", [Point(day, "cpi", value) for day, _, value in prints])
        snapshot = indicator_service.macro_snapshot(datetime.date(2026, 10, 20))
        self.assertIsNone(snapshot["cpi_yoy_pct"])
        self.assertIsNone(snapshot["cpi_surprise_pct"])

    def test_no_data_at_all(self):
        self.assertEqual(indicator_service.technical_snapshot(self.START), {"close": None})
        self.assertIsNone(indicator_service.macro_snapshot(self.START)["dxy_change_2w_pct"])
