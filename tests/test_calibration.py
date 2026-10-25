import datetime

from django.test import SimpleTestCase, TestCase

from apps.backtest import calibration
from apps.backtest.models import BacktestRun
from apps.backtest.services import calibration_service
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository


class CalibrationMathTests(SimpleTestCase):
    def test_down_calls_count_with_mirrored_confidence(self):
        self.assertEqual(calibration.confidence(30), 70)
        self.assertEqual(calibration.bucket_label(70), "70s")
        self.assertEqual(calibration.bucket_label(100), "90s")

    def test_table_groups_calls_and_scores_hits(self):
        pairs = [
            (80, 0.05), (80, 0.02), (85, -0.01), (20, -0.03),  # 80s: 3 of 4 right
            (60, -0.02), (35, 0.01),                            # 60s: both wrong
            (50, 0.10),                                         # no call
        ]
        table = calibration.calibration_table(pairs)
        self.assertEqual([b.label for b in table], ["60s", "80s"])
        sixties, eighties = table
        self.assertEqual((sixties.calls, sixties.hit_rate), (2, 0.0))
        self.assertEqual((eighties.calls, eighties.hit_rate), (4, 75.0))
        self.assertAlmostEqual(eighties.avg_confidence, 81.25)

    def test_brier_score(self):
        self.assertEqual(calibration.brier_score([(50, 0.1), (50, -0.1)]), 0.25)
        self.assertEqual(calibration.brier_score([(100, 0.1), (0, -0.1)]), 0.0)
        self.assertIsNone(calibration.brier_score([]))

    def test_forward_returns_skip_unknown_future(self):
        d = datetime.date(2026, 7, 1)
        closes = {d: 100.0, d + datetime.timedelta(days=7): 110.0}
        returns = calibration.forward_returns([d, d + datetime.timedelta(days=1)], closes, 7)
        self.assertEqual(list(returns), [d])
        self.assertAlmostEqual(returns[d], 0.1)


class CalibrationServiceTests(TestCase):
    def test_report_per_agent_is_saved(self):
        start = datetime.date(2026, 7, 1)
        market_data_repository.save_points(
            "binance", [Point(start + datetime.timedelta(days=i), "close", 100.0 + i) for i in range(12)])
        days = [start + datetime.timedelta(days=i) for i in range(5)]
        scores = {day: {"technical": 70, "macro": 40} for day in days}

        reports = calibration_service.calibrate("rules", scores, horizon=7)

        self.assertEqual(reports["technical"]["buckets"][0]["hit_rate"], 100.0)
        self.assertEqual(reports["macro"]["buckets"][0]["hit_rate"], 0.0)
        self.assertEqual(reports["technical"]["calls"], 5)
        self.assertEqual(BacktestRun.objects.filter(name__endswith=":calibration").count(), 2)
