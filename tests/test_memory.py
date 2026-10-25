import datetime
import json

from django.test import SimpleTestCase, TestCase

from apps.agents.memory import features, memory_service
from apps.agents.models import AgentRun, MemoryCase
from apps.agents.services import agent_service
from apps.agents.technical import agent as technical_agent
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from tests.fake_anthropic import FakeClient

START = datetime.date(2026, 5, 1)


def day(n):
    return START + datetime.timedelta(days=n)


class FeatureTests(SimpleTestCase):
    def test_encode_numbers_flags_and_categories(self):
        encoded = features.encode({"rsi_14": 55, "cuts_expected": True, "macd_cross_3d": "bearish",
                                   "fed_last_move_60d": "cut", "missing": None})
        self.assertEqual(encoded, {"rsi_14": 55.0, "cuts_expected": 1.0, "macd_cross_3d": -1.0,
                                   "fed_last_move_60d": -1.0})

    def test_distance_is_scaled_per_feature(self):
        scales = {"rsi_14": 10.0, "change_7d_pct": 1.0}
        query = {"rsi_14": 50.0, "change_7d_pct": 0.0}
        close_in_rsi = {"rsi_14": 60.0, "change_7d_pct": 0.0}   # 1 std apart
        close_in_pct = {"rsi_14": 50.0, "change_7d_pct": 3.0}   # 3 std apart
        self.assertLess(features.distance(query, close_in_rsi, scales), features.distance(query, close_in_pct, scales))

    def test_missing_features_count_against_a_case(self):
        query = {"a": 0.0, "b": 0.0}
        self.assertGreater(features.distance(query, {"a": 0.0}, {}), features.distance(query, {"a": 0.0, "b": 1.0}, {}))
        self.assertIsNone(features.distance({"a": 0.0, "b": 0.0, "c": 0.0}, {"a": 0.0}, {}))


class MemoryServiceTests(TestCase):
    def setUp(self):
        points = [Point(day(i), field, 100.0 + i) for i in range(80) for field in ("close", "high", "low")]
        market_data_repository.save_points("binance", points)

    def test_cases_only_for_days_with_a_known_7_day_outcome(self):
        saved = memory_service.build_cases("technical", technical_agent.model_input, day(0), day(79))
        self.assertEqual(saved, 73)  # the last 7 days have no outcome yet
        case = MemoryCase.objects.get(agent="technical", date=day(10))
        self.assertAlmostEqual(case.return_7d_pct, round((117 / 110 - 1) * 100, 2))
        self.assertIn("rose", case.outcome)
        self.assertIn("rsi_14", json.loads(case.setup_summary))

    def test_retrieval_never_uses_unfinished_cases(self):
        memory_service.build_cases("technical", technical_agent.model_input, day(0), day(79))
        decision_day = day(60)
        setup = json.loads(MemoryCase.objects.get(agent="technical", date=decision_day).setup_summary)
        found = memory_service.similar_cases("technical", decision_day, setup)
        self.assertEqual(len(found), 5)
        self.assertTrue(all(case.date <= decision_day - datetime.timedelta(days=7) for case in found))

    def test_opus_sees_similar_cases_without_dates(self):
        memory_service.build_cases("technical", technical_agent.model_input, day(0), day(79))
        client = FakeClient()
        agent_service.run_agents(day(70), ["technical"], client=client)
        sent = json.loads(client.calls[0]["messages"][0]["content"])
        self.assertEqual(len(sent["similar_past_setups"]), 5)
        self.assertEqual(set(sent["similar_past_setups"][0]), {"setup", "return_after_7d_pct"})
        self.assertNotIn("2026", client.calls[0]["messages"][0]["content"])
        self.assertIn("similar_past_setups", AgentRun.objects.get().key_data["model_input"])

    def test_no_memory_means_an_empty_list(self):
        client = FakeClient()
        agent_service.run_agents(day(70), ["technical"], client=client)
        self.assertEqual(json.loads(client.calls[0]["messages"][0]["content"])["similar_past_setups"], [])
