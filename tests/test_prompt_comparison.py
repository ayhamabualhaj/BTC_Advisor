import datetime
import json
from decimal import Decimal

from django.test import TestCase

from apps.agents.models import AgentRun, PromptVersion
from apps.backtest.services import prompt_comparison_service as pcs
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from tests.fake_anthropic import GOOD_VERDICT, FakeClient, response

START = datetime.date(2026, 1, 1)
HAIKU = "claude-haiku-5-5"


class PromptComparisonTests(TestCase):
    def setUp(self):
        points = [Point(START + datetime.timedelta(days=i), field, 100.0 + i)
                  for i in range(30) for field in ("close", "high", "low")]
        market_data_repository.save_points("binance", points)
        for agent in ("technical", "derivatives", "macro"):
            for version in (1, 2):
                PromptVersion.objects.create(agent=agent, version=version, prompt_text=f"old v{version}")
        self.found = pcs.versions(2, 3)
        self.days = [START + datetime.timedelta(days=20), START + datetime.timedelta(days=21)]

    def test_new_version_comes_from_the_files(self):
        self.assertEqual(self.found["new"]["macro"].version, 3)
        self.assertIn("Fed rate hike", self.found["new"]["macro"].prompt_text)

    def test_each_version_gets_its_own_prompt_and_input_once(self):
        client = FakeClient(response({**GOOD_VERDICT, "opus_score": 60}, input_tokens=2000, output_tokens=300))
        progress = pcs.run(HAIKU, self.found, self.days, Decimal("1"), client=client)
        self.assertEqual(progress.calls, 12)  # 2 days x 3 agents x 2 versions
        sent = {(call["system"][:6], tuple(sorted(json.loads(call["messages"][0]["content"])))) for call in client.calls}
        old_macro = next(keys for system, keys in sent if system == "old v2" and "cuts_expected" in keys)
        self.assertIn("similar_past_setups", old_macro)
        new_inputs = [keys for system, keys in sent if system != "old v2"]
        self.assertTrue(all("similar_past_days" in keys and "cuts_expected" not in keys for keys in new_inputs))
        self.assertEqual(AgentRun.objects.filter(model=HAIKU).count(), 12)
        # Nothing is asked twice.
        self.assertEqual(pcs.run(HAIKU, self.found, self.days, Decimal("1"), client=client).calls, 0)

    def test_stops_before_the_cap(self):
        progress = pcs.run(HAIKU, self.found, self.days, Decimal("0.001"), client=FakeClient())
        self.assertTrue(progress.stopped_at_cap)
        self.assertEqual(progress.calls, 0)

    def test_compares_both_versions_on_the_same_days(self):
        pcs.run(HAIKU, self.found, self.days, Decimal("1"), client=FakeClient(response({**GOOD_VERDICT, "opus_score": 60})))
        row = pcs.compare(HAIKU, self.found, self.days, horizon=1)["all"]["all"]
        # The price rises every day: every Buy is right.
        self.assertEqual((row["old"].calls, row["old"].hit_rate, row["new"].hit_rate), (6, 100, 100))
