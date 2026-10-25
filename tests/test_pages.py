import datetime
from decimal import Decimal

from django.test import TestCase

from apps.agents.models import AgentRun, PromptVersion
from apps.backtest.models import BacktestRun, Decision

DAY = datetime.date(2026, 7, 1)


class EmptyPagesTests(TestCase):
    def test_every_page_works_with_an_empty_database(self):
        for url in ("/", "/agents/technical/", "/signals/", "/backtests/", "/costs/", "/prompts/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
        self.assertContains(self.client.get("/"), "daily_run")

    def test_unknown_agent_is_404(self):
        self.assertEqual(self.client.get("/agents/nobody/").status_code, 404)


class FilledPagesTests(TestCase):
    def setUp(self):
        prompt = PromptVersion.objects.create(agent="technical", version=3, prompt_text="You are the agent")
        AgentRun.objects.create(
            date=DAY, agent="technical", rule_score=60, opus_score=71, direction="bullish",
            reasons=["Trend is up", "RSI is calm", "Support is near"],
            key_data={"rsi_14": 55.0, "rule_reasons": ["Price above 50-day average (+10)"], "skipped": []},
            suggested_stop_loss=95000, prompt_version=prompt, cost_usd=Decimal("0.05"),
        )
        Decision.objects.create(date=DAY, technical_score=71, signal="buy", threshold=60, agents_required=2)

    def test_today_shows_signal_scores_and_reasons(self):
        page = self.client.get("/").content.decode()
        for text in ("Buy", "71", "Trend is up", "$95000", "prompt v3"):
            self.assertIn(text, page)

    def test_agent_page_shows_both_scores_reasoning_and_chart_data(self):
        page = self.client.get("/agents/technical/").content.decode()
        for text in ("Opus reasoning", "Price above 50-day average", "rsi_14", 'id="score-data"'):
            self.assertIn(text, page)

    def test_backtests_page_lists_runs_calibration_and_rule(self):
        BacktestRun.objects.create(name="rules:technical", start_date=DAY, end_date=DAY, trade_count=2,
                                   win_rate=50, total_profit_pct=3.5, max_drawdown_pct=1, buy_and_hold_pct=4,
                                   settings={"threshold": 60})
        BacktestRun.objects.create(name="rules:technical:calibration", start_date=DAY, end_date=DAY, settings={
            "score_type": "rules", "agent": "technical", "calls": 9, "brier_score": 0.3,
            "buckets": [{"label": "60s", "calls": 9, "hit_rate": 44.4, "avg_confidence": 61}]})
        BacktestRun.objects.create(name="rules:combining_rule", start_date=DAY, end_date=DAY, settings={
            "score_type": "rules", "threshold": 60, "agents_required": 2, "first_half_pct": 1, "second_half_pct": 2})
        page = self.client.get("/backtests/").content.decode()
        for text in ("rules:technical", "3.50%", "60s", "44%", "buy when 2 agents score"):
            self.assertIn(text, page)

    def test_costs_and_prompts_pages(self):
        self.assertContains(self.client.get("/costs/"), "$0.05")
        self.assertContains(self.client.get("/prompts/"), "You are the agent")


class SignalsPageTests(TestCase):
    """Price falls 1 a day, so every Buy is wrong and every Sell is right after 7 days."""

    def setUp(self):
        from apps.data.collectors.base import Point
        from apps.data.repositories import market_data_repository

        start = DAY - datetime.timedelta(days=60)
        points = [Point(start + datetime.timedelta(days=i), field, 200.0 - i)
                  for i in range(75) for field in ("close", "high", "low")]
        market_data_repository.save_points("binance", points)
        prompt = PromptVersion.objects.create(agent="macro", version=2, prompt_text="p")
        for offset, score in ((0, 70), (1, 30), (2, 50)):
            AgentRun.objects.create(date=DAY + datetime.timedelta(days=offset), agent="macro", rule_score=50,
                                    opus_score=score, direction="neutral", reasons=[], key_data={},
                                    prompt_version=prompt, is_backtest=True)

    def test_judges_opus_calls_against_the_price(self):
        from apps.dashboard.services import signal_service

        table = signal_service.signal_table(DAY, DAY + datetime.timedelta(days=2))
        calls = {row["date"]: row["calls"]["macro:opus"] for row in table["rows"]}
        self.assertEqual((calls[DAY].signal, calls[DAY].outcome), ("buy", "wrong"))
        self.assertEqual((calls[DAY + datetime.timedelta(days=1)].signal,
                          calls[DAY + datetime.timedelta(days=1)].outcome), ("sell", "right"))
        self.assertEqual(calls[DAY + datetime.timedelta(days=2)].outcome, "none")  # a Hold is never judged
        self.assertEqual(calls[DAY].note, "prompt v2")
        self.assertEqual(table["summary"]["macro:opus"],
                         {"right": 1, "wrong": 1, "pending": 0, "hit_rate": 50.0})
        # Newest day first, and the last days wait for their 7-day price.
        self.assertEqual(table["rows"][0]["date"], DAY + datetime.timedelta(days=2))

    def test_last_days_are_pending(self):
        from apps.dashboard.services import signal_service

        self.assertEqual(signal_service.judge("buy", None), "pending")
        self.assertEqual(signal_service.judge("hold", 0.05), "none")
        self.assertEqual(signal_service.judge("sell", 0.05), "wrong")

    def test_page_shows_colored_calls_and_filters(self):
        page = self.client.get(f"/signals/?opus=1&start={DAY}&end={DAY + datetime.timedelta(days=2)}").content.decode()
        for text in ("call-wrong", "call-right", "▲ Buy", "▼ Sell", "Days with Opus", "-5.00%"):
            self.assertIn(text, page)
        self.assertEqual(self.client.get("/signals/?horizon=99&start=junk").status_code, 200)
