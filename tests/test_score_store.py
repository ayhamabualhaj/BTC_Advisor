import datetime
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.backtest.models import DailyScore
from apps.backtest.services import score_store
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository

START = datetime.date(2026, 1, 1)


class ScoreStoreTests(TestCase):
    def setUp(self):
        points = [Point(START + datetime.timedelta(days=i), "close", 100.0 + i) for i in range(60)]
        market_data_repository.save_points("binance", points)
        self.days = [START + datetime.timedelta(days=i) for i in range(40, 45)]

    def test_scores_are_computed_once_then_read_back(self):
        first = score_store.scores(self.days)
        self.assertEqual(DailyScore.objects.count(), 20)  # 5 days x 4 rule agents; stress has no ML score yet
        with mock.patch("apps.backtest.services.score_history.rule_and_ml_scores") as compute:
            again = score_store.scores(self.days)
        compute.assert_not_called()
        self.assertEqual(first[0], again[0])

    def test_changed_code_means_new_scores(self):
        score_store.scores(self.days)
        with mock.patch.object(score_store, "fingerprint", return_value="other-code"):
            score_store.scores(self.days)
        self.assertEqual(set(DailyScore.objects.values_list("fingerprint", flat=True)), {"other-code"})

    def test_recent_days_are_not_stored(self):
        recent = [datetime.date.today() - datetime.timedelta(days=2)]
        score_store.scores(recent)
        self.assertFalse(DailyScore.objects.filter(date=recent[0]).exists())

    def test_recent_days_are_kept_in_memory_until_new_data_arrives(self):
        cache.clear()
        recent = [datetime.date.today() - datetime.timedelta(days=2)]
        score_store.scores(recent)
        with mock.patch("apps.backtest.services.score_history.rule_and_ml_scores") as compute:
            score_store.scores(recent)
        compute.assert_not_called()
        market_data_repository.save_points("binance", [Point(recent[0], "close", 1.0)])
        with mock.patch("apps.backtest.services.score_history.rule_and_ml_scores",
                        return_value=({recent[0]: {}}, {recent[0]: {}})) as compute:
            score_store.scores(recent)
        compute.assert_called_once()
