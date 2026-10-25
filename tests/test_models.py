import datetime

from django.db import IntegrityError
from django.test import TestCase

from apps.agents.models import AgentName, AgentRun, PromptVersion, PromptVersionLocked
from apps.backtest.models import Decision, Outcome
from apps.data.models import MarketData

DAY = datetime.date(2026, 7, 1)


class MarketDataTests(TestCase):
    def test_same_point_twice_is_rejected(self):
        MarketData.objects.create(date=DAY, source="binance", field="close", value=1.0)
        with self.assertRaises(IntegrityError):
            MarketData.objects.create(date=DAY, source="binance", field="close", value=2.0)

    def test_other_field_same_day_is_allowed(self):
        MarketData.objects.create(date=DAY, source="binance", field="close", value=1.0)
        MarketData.objects.create(date=DAY, source="binance", field="open", value=1.0)
        self.assertEqual(MarketData.objects.count(), 2)


class PromptVersionTests(TestCase):
    def make_prompt(self, version=1, text="v1"):
        return PromptVersion.objects.create(agent=AgentName.TECHNICAL, version=version, prompt_text=text)

    def test_changing_saved_text_is_refused(self):
        prompt = self.make_prompt()
        prompt.prompt_text = "edited"
        with self.assertRaises(PromptVersionLocked):
            prompt.save()

    def test_notes_can_still_be_edited(self):
        prompt = self.make_prompt()
        prompt.notes = "worked well"
        prompt.save()
        prompt.refresh_from_db()
        self.assertEqual(prompt.notes, "worked well")

    def test_same_version_twice_is_rejected(self):
        self.make_prompt()
        with self.assertRaises(IntegrityError):
            self.make_prompt(text="other")

    def test_runs_link_to_their_prompt(self):
        prompt = self.make_prompt()
        AgentRun.objects.create(date=DAY, agent=AgentName.TECHNICAL, rule_score=60, prompt_version=prompt)
        self.assertEqual(prompt.runs.count(), 1)


class AgentRunTests(TestCase):
    def test_rule_only_run_needs_no_opus_fields(self):
        run = AgentRun.objects.create(date=DAY, agent=AgentName.MACRO, rule_score=55)
        self.assertIsNone(run.opus_score)
        self.assertEqual((run.reasons, run.key_data, run.input_tokens), ([], {}, 0))


class BacktestModelTests(TestCase):
    def test_decision_display(self):
        decision = Decision.objects.create(date=DAY, signal=Decision.Signal.BUY, threshold=65)
        self.assertEqual(str(decision), "2026-07-01: Buy")

    def test_one_outcome_per_date(self):
        Outcome.objects.create(date=DAY, price_at_decision=100)
        with self.assertRaises(IntegrityError):
            Outcome.objects.create(date=DAY, price_at_decision=101)
