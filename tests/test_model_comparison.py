import datetime
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from ai import opus_client
from apps.agents.models import AgentRun, PromptVersion
from apps.backtest.services import model_comparison_service as mcs
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from tests.fake_anthropic import GOOD_VERDICT, FakeClient, response

DAY = datetime.date(2026, 7, 1)
HAIKU = "claude-haiku-5-5"


class PriceTests(SimpleTestCase):
    def test_each_model_has_its_own_prices(self):
        self.assertEqual(opus_client.cost_usd(1_000_000, 0, "claude-opus-5-5"), Decimal("4"))
        self.assertEqual(opus_client.cost_usd(1_000_000, 1_000_000, HAIKU), Decimal("0.60"))

    def test_a_model_without_prices_is_never_called(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            opus_client.ask("system", {}, client=client, model="claude-unknown")
        self.assertEqual(client.calls, [])


class ReplayTests(TestCase):
    def setUp(self):
        # The price rises every day, so a Buy is right and a Sell wrong.
        points = [Point(DAY + datetime.timedelta(days=i), "close", 100.0 + i) for i in range(20)]
        market_data_repository.save_points("binance", points)
        self.prompt = PromptVersion.objects.create(agent="macro", version=2, prompt_text="the exact v2 prompt")
        for offset, score in ((0, 70), (1, 30)):
            AgentRun.objects.create(date=DAY + datetime.timedelta(days=offset), agent="macro", rule_score=50,
                                    opus_score=score, key_data={"model_input": {"cpi_yoy_pct": 3.0 + offset}},
                                    prompt_version=self.prompt, model="claude-opus-5-5", is_backtest=True,
                                    input_tokens=2000, output_tokens=300, cost_usd=Decimal("0.014"))

    def test_asks_the_same_prompt_and_input_once(self):
        client = FakeClient(response({**GOOD_VERDICT, "opus_score": 60}, input_tokens=2000, output_tokens=400))
        progress = mcs.replay(HAIKU, Decimal("1"), client=client)
        self.assertEqual(progress.calls, 2)
        self.assertEqual(client.calls[0]["model"], HAIKU)
        self.assertEqual(client.calls[0]["system"], "the exact v2 prompt")
        self.assertIn('"cpi_yoy_pct": 3.0', client.calls[0]["messages"][0]["content"])
        run = AgentRun.objects.get(model=HAIKU, date=DAY)
        self.assertEqual((run.opus_score, run.prompt_version, run.cost_usd), (60, self.prompt, Decimal("0.0004")))
        # Done days are never paid for twice.
        self.assertEqual(mcs.replay(HAIKU, Decimal("1"), client=client).calls, 0)

    def test_stops_before_the_cap(self):
        progress = mcs.replay(HAIKU, Decimal("0.0001"), client=FakeClient())
        self.assertTrue(progress.stopped_at_cap)
        self.assertEqual(progress.calls, 0)

    def test_compares_both_models_on_the_same_days(self):
        mcs.replay(HAIKU, Decimal("1"), client=FakeClient(response({**GOOD_VERDICT, "opus_score": 60})))
        row = mcs.compare(HAIKU, horizon=1)["macro"]
        # Opus: Buy right, Sell wrong. Haiku: Buy right twice.
        self.assertEqual((row["reference"].calls, row["reference"].hit_rate), (2, 50))
        self.assertEqual((row["other"].calls, row["other"].hit_rate), (2, 100))
        self.assertEqual(row["same_side"], 1)
        self.assertEqual(row["gap"], 20)


class ModelPageTests(TestCase):
    def test_empty_until_another_model_answered(self):
        page = self.client.get("/models/").content.decode()
        self.assertIn("compare_models --estimate", page)

    def test_all_agents_on_one_page_with_tabs(self):
        ReplayTests.setUp(self)
        mcs.replay(HAIKU, Decimal("1"), client=FakeClient(response({**GOOD_VERDICT, "opus_score": 60})))
        page = self.client.get("/models/?horizon=1").content.decode()
        for text in ("Opus 5.5 vs Haiku 5.5", 'data-tab="all"', 'data-tab="macro"', 'id="panel-macro"',
                     "model-chart-data", "▲ Buy", "✓ won", "1 / 2"):
            self.assertIn(text, page)
