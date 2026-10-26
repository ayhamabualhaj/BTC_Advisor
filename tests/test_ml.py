import datetime

from django.test import SimpleTestCase, TestCase

from ai import flow, ml
from ai.brief import Brief
from apps.agents.models import AgentRun, MemoryCase
from apps.agents.services import agent_service, memory_service
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from tests.fake_anthropic import FakeClient

START = datetime.date(2026, 1, 1)


def day(n):
    return START + datetime.timedelta(days=n)


def cases(count):
    """A pattern to learn: the price rose after every day with a positive x."""
    return [({"x": float(x), "noise": float(i % 3), "flat": 1.0}, x > 0)
            for i, x in enumerate([(-1) ** i * (1 + i % 4) for i in range(count)])]


class MLModelTests(SimpleTestCase):
    def test_too_few_past_days_means_no_score(self):
        result = ml.score({"x": 1.0}, cases(ml.MIN_CASES - 1))
        self.assertIsNone(result.score)
        self.assertIn("needs", result.reasons[0])

    def test_learns_which_way_a_feature_points(self):
        training = cases(200)
        up = ml.score({"x": 3.0, "noise": 1.0}, training, regularization=1.0)
        down = ml.score({"x": -3.0, "noise": 1.0}, training, regularization=1.0)
        self.assertGreater(up.score, 55)
        self.assertLess(down.score, 45)
        self.assertIn("x = 3", up.reasons[1])

    def test_strong_regularization_stays_closer_to_fifty(self):
        training = cases(200)
        loose = ml.score({"x": 3.0}, training, regularization=1.0).score
        default = ml.score({"x": 3.0}, training).score
        self.assertLess(abs(default - 50), abs(loose - 50))

    def test_a_feature_never_seen_in_training_does_not_break_it(self):
        result = ml.score({"x": 3.0, "brand_new": 7.0}, cases(200))
        self.assertIsNotNone(result.score)

    def test_the_forest_learns_too_and_names_its_main_features(self):
        training = cases(400)
        up = ml.score({"x": 3.0, "noise": 1.0}, training, build=ml.forest)
        down = ml.score({"x": -3.0, "noise": 1.0}, training, build=ml.forest)
        self.assertGreater(up.score, down.score)
        self.assertIn("x = 3", up.reasons[1])

    def test_monthly_cutoff_is_before_the_month_began(self):
        self.assertEqual(ml.monthly_cutoff(datetime.date(2026, 3, 20)), datetime.date(2026, 2, 21))
        self.assertEqual(ml.daily_cutoff(datetime.date(2026, 3, 20)), datetime.date(2026, 3, 13))

    def test_one_sided_history_gives_no_score(self):
        training = [({"x": 1.0}, True)] * ml.MIN_CASES
        self.assertIsNone(ml.score({"x": 1.0}, training).score)


class TrainingCutoffTests(TestCase):
    def test_only_cases_with_a_known_outcome_are_learned_from(self):
        for n in range(30):
            MemoryCase.objects.create(date=day(n), agent="technical", setup_summary="{}",
                                      ml_features={"x": float(n), "y": 1.0, "z": 2.0}, outcome="",
                                      return_7d_pct=1.0)
        MemoryCase.objects.filter(date=day(5)).update(ml_features={})  # a day with no numbers
        training = memory_service.training_cases("technical", day(20))
        # Cases dated day 0..13 (the outcome of day 13 is known at the close of day 20),
        # minus day 5, which has no numbers to learn from.
        self.assertEqual(len(training), 13)
        self.assertEqual(max(features["x"] for features, _ in training), 13.0)

    def test_macro_learns_only_from_before_the_month(self):
        for n in range(30):
            MemoryCase.objects.create(date=day(n), agent="macro", setup_summary="{}",
                                      ml_features={"x": float(n), "y": 1.0, "z": 2.0}, return_7d_pct=1.0)
        # Decision on Jan 30: the month began Jan 1, so only cases up to Dec 24 count: none.
        self.assertEqual(memory_service.training_cases("macro", day(29)), [])
        # Decision on Feb 1: cases up to Jan 24.
        self.assertEqual(len(memory_service.training_cases("macro", day(31))), 24)


class AdvisorFlowTests(TestCase):
    def setUp(self):
        points = [Point(day(i), field, 100.0 + i) for i in range(60) for field in ("close", "high", "low")]
        market_data_repository.save_points("binance", points)

    def test_without_opus_no_api_call_is_made(self):
        client = FakeClient()
        runs = agent_service.run_agents(day(59), use_opus=False, client=client)
        self.assertEqual(client.calls, [])
        self.assertEqual([run.agent for run in runs], ["technical", "derivatives", "macro", "stress", "riskon"])
        run = AgentRun.objects.get(agent="technical")
        self.assertEqual((run.rule_score, run.opus_score, run.prompt_version), (60, None, None))
        # No memory yet, so the ML agent abstains and says why.
        self.assertIsNone(run.ml_score)
        self.assertIn("past days", run.key_data["ml_reasons"][0])

    def test_ml_scores_once_there_is_memory(self):
        for n, (features, went_up) in enumerate(cases(200)):
            MemoryCase.objects.create(date=day(-300 + n), agent="technical", setup_summary="{}",
                                      ml_features=features, outcome="", return_7d_pct=1.0 if went_up else -1.0)
        [run] = agent_service.run_agents(day(59), ["technical"], use_opus=False)
        self.assertIsNotNone(run.ml_score)

    def test_flow_returns_one_verdict_per_brief_in_order(self):
        briefs = {agent: Brief(agent, day(59), {}, {}) for agent in ("macro", "technical")}
        verdicts = flow.run(briefs, use_opus=False)
        self.assertEqual([verdict.agent for verdict in verdicts], ["macro", "technical"])
        self.assertTrue(all(verdict.opus is None for verdict in verdicts))
