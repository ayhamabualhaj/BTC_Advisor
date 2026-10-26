import datetime
import json
from decimal import Decimal

import anthropic
import httpx2
from django.test import SimpleTestCase, TestCase, override_settings

from ai import opus_client
from ai.derivatives import inputs as derivatives_inputs
from ai.macro import inputs as macro_inputs
from ai.technical import inputs as technical_inputs, opus as technical_opus
from apps.agents.models import AgentRun, PromptVersion
from apps.agents.services import agent_service, prompt_service
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository
from tests.fake_anthropic import GOOD_VERDICT, FakeClient, response

DAY = datetime.date(2026, 7, 31)


class OpusClientTests(SimpleTestCase):
    def test_valid_reply_with_tokens_and_cost(self):
        client = FakeClient(response(input_tokens=2000, output_tokens=1000))
        reply = opus_client.ask("system", {"rsi_14": 50}, client)
        self.assertEqual(reply.data, GOOD_VERDICT)
        self.assertEqual((reply.input_tokens, reply.output_tokens, reply.error), (2000, 1000, ""))
        # 2000 x $4/M + 1000 x $20/M
        self.assertEqual(reply.cost_usd, Decimal("0.028"))

    @override_settings(AI_MODEL="claude-opus-5-5", AI_EFFORT="medium")
    def test_request_uses_opus_structured_output_and_effort(self):
        client = FakeClient()
        opus_client.ask("the prompt", {"b": 1, "a": 2}, client)
        call = client.calls[0]
        self.assertEqual(call["model"], "claude-opus-5-5")
        self.assertEqual(call["system"], "the prompt")
        self.assertEqual(call["output_config"]["format"]["schema"], opus_client.OUTPUT_SCHEMA)
        self.assertEqual(call["output_config"]["effort"], "medium")
        # Sorted keys keep the message identical for identical data.
        self.assertEqual(json.loads(call["messages"][0]["content"]), {"a": 2, "b": 1})

    def test_invalid_reply_is_retried_once(self):
        client = FakeClient(response({**GOOD_VERDICT, "reasons": ["only one"]}), response())
        reply = opus_client.ask("system", {}, client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(reply.data, GOOD_VERDICT)
        self.assertEqual(reply.input_tokens, 2000)  # both attempts are paid for

    def test_two_invalid_replies_give_an_error(self):
        client = FakeClient(response("not json"), response(stop_reason="max_tokens"))
        reply = opus_client.ask("system", {}, client)
        self.assertIsNone(reply.data)
        self.assertIn("max_tokens", reply.error)
        self.assertEqual(len(client.calls), 2)

    def test_api_error_is_recorded_not_raised(self):
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        client = FakeClient(anthropic.APIConnectionError(request=request))
        reply = opus_client.ask("system", {}, client)
        self.assertIsNone(reply.data)
        self.assertIn("API error", reply.error)

    def test_validation_rules(self):
        bad = [
            {**GOOD_VERDICT, "opus_score": 101},
            {**GOOD_VERDICT, "opus_score": 60.5},
            {**GOOD_VERDICT, "reasons": ["a", "b", "c", "d", "e", "f"]},
            {**GOOD_VERDICT, "suggested_stop_loss_pct": 0},
            {**GOOD_VERDICT, "extra": 1},
        ]
        for data in bad:
            with self.assertRaises(opus_client.InvalidReply, msg=data):
                opus_client.validate(data)


class ModelInputTests(SimpleTestCase):
    def test_technical_input_has_no_absolute_prices(self):
        snapshot = {"close": 110.0, "sma_20": 105.0, "sma_50": 100.0, "sma_200": 88.0, "rsi_14": 55.0,
                    "macd_cross_3d": None, "change_7d_pct": 1.0, "change_30d_pct": 5.0,
                    "support": 104.5, "resistance": 121.0}
        data = technical_inputs.model_input(snapshot)
        self.assertEqual(data["price_vs_sma_50_pct"], 10.0)
        self.assertEqual(data["price_vs_sma_20_pct"], 4.76)
        self.assertEqual(data["sma_50_vs_sma_200_pct"], 13.64)
        self.assertEqual(data["support_distance_pct"], 5.0)
        self.assertEqual(data["resistance_distance_pct"], 10.0)
        self.assertNotIn(110.0, data.values())

    def test_inputs_survive_missing_data(self):
        for module in (technical_inputs, derivatives_inputs, macro_inputs):
            data = module.model_input({})
            self.assertTrue(all(value is None for value in data.values()), module.__name__)

    def test_derivatives_units(self):
        data = derivatives_inputs.model_input({"funding_rate": 0.0001, "long_liquidations_usd_1d": 25_000_000})
        self.assertEqual((data["funding_rate_8h_pct"], data["long_liquidations_musd_1d"]), (0.01, 25.0))

    def test_macro_spread_and_fed_move(self):
        data = macro_inputs.model_input({"treasury_2y": 3.5, "fed_funds_effective": 4.33, "fed_rate_change_60d": -1})
        self.assertEqual((data["two_year_minus_fed_funds_pct"], data["fed_last_move_60d"]), (-0.83, "cut"))


class PromptVersionTests(TestCase):
    def test_same_text_reuses_the_version(self):
        first = prompt_service.current_version("technical", technical_opus.PROMPT_FILE)
        again = prompt_service.current_version("technical", technical_opus.PROMPT_FILE)
        self.assertEqual((first.pk, first.version), (again.pk, 1))
        self.assertIn("How to answer", first.prompt_text)

    def test_changed_text_creates_a_new_version(self):
        PromptVersion.objects.create(agent="technical", version=1, prompt_text="an older prompt")
        current = prompt_service.current_version("technical", technical_opus.PROMPT_FILE)
        self.assertEqual(current.version, 2)
        self.assertEqual(PromptVersion.objects.get(version=1).prompt_text, "an older prompt")


class AgentRunTests(TestCase):
    def setUp(self):
        start = DAY - datetime.timedelta(days=59)
        points = [Point(start + datetime.timedelta(days=i), field, 100.0 + i)
                  for i in range(60) for field in ("close", "high", "low")]
        market_data_repository.save_points("binance", points)

    def test_each_agent_saves_one_run_with_both_scores(self):
        client = FakeClient()
        runs = agent_service.run_agents(DAY, client=client)

        self.assertEqual([run.agent for run in runs], ["technical", "derivatives", "macro"])
        self.assertEqual(len(client.calls), 3)
        run = AgentRun.objects.get(agent="technical")
        self.assertEqual((run.rule_score, run.opus_score, run.direction), (60, 62, "bullish"))
        self.assertEqual(run.prompt_version.version, 1)
        self.assertEqual(run.suggested_stop_loss, round(159.0 * 0.95, 2))
        self.assertEqual((run.input_tokens, run.output_tokens), (1000, 500))
        self.assertEqual(run.cost_usd, Decimal("0.014"))

    def test_agents_do_not_see_each_others_results_or_the_rule_score(self):
        client = FakeClient()
        agent_service.run_agents(DAY, client=client)
        for call in client.calls:
            message = call["messages"][0]["content"]
            self.assertNotIn("rule_score", message)
            self.assertNotIn("opus_score", message)
            self.assertNotIn("2026", message)

    def test_failed_opus_call_keeps_the_rule_result(self):
        client = FakeClient(response("broken"))
        [run] = agent_service.run_agents(DAY, ["technical"], client=client)
        self.assertIsNone(run.opus_score)
        self.assertEqual(run.direction, "bullish")  # the rule direction stands in
        self.assertIn("Invalid reply", run.error)
        self.assertEqual(run.input_tokens, 2000)

    def test_output_matches_the_plan(self):
        [run] = agent_service.run_agents(DAY, ["technical"], client=FakeClient())
        output = run.as_output()
        self.assertEqual(set(output), {
            "agent", "date", "rule_score", "ml_score", "opus_score", "direction", "reasons", "key_data",
            "suggested_stop_loss", "prompt_version", "input_tokens", "output_tokens", "cost_usd",
        })
        self.assertEqual(output["date"], "2026-07-31")
        self.assertNotIn("model_input", output["key_data"])
