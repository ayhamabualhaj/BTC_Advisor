import datetime

from django.test import TestCase, override_settings

from apps.agents.models import AgentRun
from apps.backtest.models import Decision, Outcome
from apps.backtest.services import daily_run_service, outcome_service
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from tests.fake_anthropic import FakeClient

START = datetime.date(2026, 6, 1)
DAY = datetime.date(2026, 7, 20)


def save_prices(days=60, step=1.0):
    points = [Point(START + datetime.timedelta(days=i), field, 100.0 + i * step)
              for i in range(days) for field in ("close", "high", "low")]
    market_data_repository.save_points("binance", points)


@override_settings(ANTHROPIC_API_KEY="")
class DailyRunTests(TestCase):
    def setUp(self):
        save_prices()

    def test_with_opus(self):
        report = daily_run_service.run(DAY, client=FakeClient(), collect=False)
        self.assertTrue(report.used_opus)
        self.assertEqual(AgentRun.objects.filter(date=DAY, opus_score=62).count(), 3)
        # The default vote uses the rule scores; the Opus score is saved on the run.
        self.assertEqual(Decision.objects.get(date=DAY).technical_score, AgentRun.objects.get(date=DAY, agent="technical").rule_score)
        self.assertEqual(report.outcomes_updated, 1)

    def test_without_credentials_runs_rules_only(self):
        report = daily_run_service.run(DAY, collect=False)
        self.assertFalse(report.used_opus)
        self.assertEqual(AgentRun.objects.filter(date=DAY, opus_score__isnull=True).count(), 3)
        self.assertEqual(Decision.objects.count(), 1)

    def test_same_day_twice_needs_force(self):
        daily_run_service.run(DAY, collect=False)
        with self.assertRaises(daily_run_service.DailyRunError):
            daily_run_service.run(DAY, collect=False)
        daily_run_service.run(DAY, collect=False, force=True)
        self.assertEqual(Decision.objects.count(), 2)

    def test_no_price_for_the_day_stops_before_any_call(self):
        client = FakeClient()
        with self.assertRaises(daily_run_service.DailyRunError):
            daily_run_service.run(START + datetime.timedelta(days=90), client=client, collect=False)
        self.assertEqual(client.calls, [])


class OutcomeTests(TestCase):
    def test_prices_and_correctness_after_7_days(self):
        save_prices()  # price rises every day
        AgentRun.objects.create(date=DAY, agent="technical", rule_score=40, opus_score=70)  # opus wins
        AgentRun.objects.create(date=DAY, agent="macro", rule_score=35)                    # rules only, wrong
        AgentRun.objects.create(date=DAY, agent="derivatives", rule_score=50)              # no call

        self.assertEqual(outcome_service.update_outcomes(), 1)

        outcome = Outcome.objects.get(date=DAY)
        offset = (DAY - START).days
        self.assertEqual((outcome.price_at_decision, outcome.price_after_7d), (100.0 + offset, 107.0 + offset))
        self.assertEqual((outcome.technical_correct, outcome.macro_correct, outcome.derivatives_correct),
                         (True, False, None))

    def test_unknown_future_stays_empty(self):
        save_prices(days=52)  # ends 2026-07-22, before DAY + 7
        AgentRun.objects.create(date=DAY, agent="technical", rule_score=60)
        outcome_service.update_outcomes()
        outcome = Outcome.objects.get(date=DAY)
        self.assertIsNotNone(outcome.price_after_1d)
        self.assertIsNone(outcome.price_after_7d)
        self.assertIsNone(outcome.technical_correct)
