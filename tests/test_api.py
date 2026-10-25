import datetime
from decimal import Decimal

from django.test import TestCase

from apps.agents.models import AgentRun, PromptVersion
from apps.backtest.models import BacktestRun, Decision
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository

DAY = datetime.date(2026, 7, 1)


class ApiTests(TestCase):
    def setUp(self):
        self.prompt = PromptVersion.objects.create(agent="technical", version=1, prompt_text="p")
        self.run = AgentRun.objects.create(
            date=DAY, agent="technical", rule_score=60, opus_score=70, direction="bullish",
            prompt_version=self.prompt, input_tokens=1000, output_tokens=500, cost_usd=Decimal("0.014"),
        )
        AgentRun.objects.create(date=DAY, agent="technical", rule_score=55, opus_score=40,
                                prompt_version=self.prompt, is_backtest=True, cost_usd=Decimal("0.02"))

    def get(self, url):
        return self.client.get(url)

    def test_today_without_any_runs_is_404(self):
        AgentRun.objects.all().delete()
        self.assertEqual(self.get("/api/decision/today/").status_code, 404)

    def test_today_returns_decision_and_live_runs(self):
        Decision.objects.create(date=DAY, technical_score=70, signal="no_trade", threshold=60)
        data = self.get("/api/decision/today/").json()
        self.assertEqual(data["decision"]["signal"], "no_trade")
        self.assertEqual([run["opus_score"] for run in data["agent_runs"]], [70])
        self.assertEqual(data["agent_runs"][0]["prompt_version"], 1)

    def test_agent_runs_filters(self):
        self.assertEqual(self.get("/api/agent-runs/").json()["count"], 2)
        self.assertEqual(self.get("/api/agent-runs/?backtest=false").json()["count"], 1)
        self.assertEqual(self.get("/api/agent-runs/?agent=macro").json()["count"], 0)
        self.assertEqual(self.get("/api/agent-runs/?agent=nope").status_code, 400)
        self.assertEqual(self.get("/api/agent-runs/?date=July").status_code, 400)

    def test_backtests_filter_by_name(self):
        BacktestRun.objects.create(name="rules:macro", start_date=DAY, end_date=DAY)
        BacktestRun.objects.create(name="opus:macro", start_date=DAY, end_date=DAY)
        self.assertEqual([r["name"] for r in self.get("/api/backtests/?name=opus").json()["results"]],
                         ["opus:macro"])

    def test_costs_split_live_and_backtest(self):
        data = self.get("/api/costs/").json()
        self.assertEqual(Decimal(str(data["total_usd"])), Decimal("0.034"))
        self.assertEqual([(row["is_backtest"], row["calls"]) for row in data["by_agent"]], [(False, 1), (True, 1)])
        self.assertEqual(sum(row["calls"] for row in data["by_day"]), 2)

    def test_prompt_history_with_hit_rate(self):
        # Up 10% after 7 days: the 70 call was right, the 40 call wrong.
        market_data_repository.save_points("binance", [
            Point(DAY, "close", 100.0), Point(DAY + datetime.timedelta(days=7), "close", 110.0)])
        [entry] = self.get("/api/prompts/?agent=technical").json()
        self.assertEqual((entry["version"]["version"], entry["runs"], entry["backtest_runs"]), (1, 2, 1))
        self.assertEqual((entry["hit_rate_7d"], entry["judged_calls"]), (50.0, 2))
        self.assertEqual(entry["avg_opus_score"], 55.0)

    def test_api_is_read_only(self):
        response = self.client.post("/api/agent-runs/", {})
        self.assertEqual(response.status_code, 405)
