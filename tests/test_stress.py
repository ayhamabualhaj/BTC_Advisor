"""The financial stress domain: data dating, snapshot, its ML-only agent and how it is judged."""

import datetime

from django.test import SimpleTestCase, TestCase

from ai import stress
from ai.domains import has, with_kind
from apps.agents.models import AgentRun
from apps.backtest.services import outcome_service
from apps.data.collectors import fred
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from apps.data.services import indicator_service

DAY = datetime.date(2026, 3, 2)


class StressDataTests(SimpleTestCase):
    def test_weekly_nfci_is_dated_when_it_was_published(self):
        # The week to Friday Feb 20, first published on Wednesday Feb 25.
        points = fred.parse_first_release([{"date": "2026-02-20", "realtime_start": "2026-02-25", "value": "-0.5"}], "nfci")
        self.assertEqual(points[0].date, datetime.date(2026, 2, 25))

    def test_stress_has_only_an_ml_agent(self):
        self.assertTrue(has("stress", "ml"))
        self.assertFalse(has("stress", "rules"))
        self.assertFalse(has("stress", "opus"))
        self.assertNotIn("stress", with_kind("opus"))
        self.assertIn("stress", with_kind("ml"))


class StressSnapshotTests(TestCase):
    def setUp(self):
        days = [DAY - datetime.timedelta(days=i) for i in range(30)]
        market_data_repository.save_points("fred", [Point(d, "vix", 30.0 - i * 0.5) for i, d in enumerate(days)])
        market_data_repository.save_points("yahoo", [Point(d, "move_close", 100.0) for d in days])
        # NFCI arrives weekly; 10 days old is still current.
        market_data_repository.save_points("fred", [Point(DAY - datetime.timedelta(days=10), "nfci", -0.4)])

    def test_snapshot_reads_known_values_only(self):
        snapshot = indicator_service.stress_snapshot(DAY)
        self.assertEqual(snapshot["vix"], 30.0)
        self.assertEqual(snapshot["vix_change_20d"], 10.0)  # 30 now, 20 twenty values ago
        self.assertEqual(snapshot["move_change_20d_pct"], 0.0)
        self.assertEqual(snapshot["nfci"], -0.4)
        self.assertEqual(stress.inputs.model_input(snapshot)["vix"], 30.0)
        earlier = indicator_service.stress_snapshot(DAY - datetime.timedelta(days=40))
        self.assertIsNone(earlier["vix"])

    def test_old_nfci_counts_as_missing(self):
        later = DAY + datetime.timedelta(days=10)
        self.assertIsNone(indicator_service.stress_snapshot(later)["nfci"])


class StressOutcomeTests(TestCase):
    def test_an_ml_only_agent_is_judged_on_its_ml_score(self):
        market_data_repository.save_points("binance", [Point(DAY, "close", 100.0),
                                                       Point(DAY + datetime.timedelta(days=7), "close", 110.0)])
        AgentRun.objects.create(date=DAY, agent="stress", rule_score=None, ml_score=70)
        self.assertTrue(outcome_service.agent_correct(DAY, "stress", 0.1))
        self.assertFalse(outcome_service.agent_correct(DAY, "stress", -0.1))
