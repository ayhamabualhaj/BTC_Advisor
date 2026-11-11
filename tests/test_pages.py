import datetime
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings

from apps.agents.models import AgentRun, PromptVersion
from apps.backtest.models import BacktestRun, Decision
from apps.backtest.services import daily_run_service

DAY = datetime.date(2026, 7, 1)


class EmptyPagesTests(TestCase):
    def test_every_page_works_with_an_empty_database(self):
        for url in ("/", "/btc/agents/technical/", "/btc/signals/", "/btc/signals/overview/", "/btc/backtests/", "/btc/costs/", "/btc/prompts/", "/btc/profit/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
        self.assertContains(self.client.get("/btc/"), "daily_run")

    def test_unknown_agent_is_404(self):
        self.assertEqual(self.client.get("/btc/agents/nobody/").status_code, 404)


class FilledPagesTests(TestCase):
    def setUp(self):
        prompt = PromptVersion.objects.create(agent="technical", version=3, prompt_text="You are the agent")
        AgentRun.objects.create(
            date=DAY, agent="technical", rule_score=60, opus_score=71, direction="bullish",
            reasons=["Trend is up", "RSI is calm", "Support is near"],
            key_data={"rsi_14": 55.0, "rule_reasons": ["Price above 50-day average (+10)"], "skipped": []},
            suggested_stop_loss=95000, prompt_version=prompt, cost_usd=Decimal("0.05"),
        )
        Decision.objects.create(date=DAY, technical_score=71, signal="buy", net_votes=2,
                                rule={"group_lead": 1, "overall": "all agree"},
                                group_calls={"rules": "buy", "ml": "buy", "opus": "hold", "stress": "buy", "riskon": "none"})

    def test_today_shows_signal_scores_and_reasons(self):
        page = self.client.get("/btc/").content.decode()
        for text in ("Buy", "71", "Trend is up", "$95,000", "prompt v3", "Who voted", "3 of 5 must agree",
                     "3 Buy · 0 Sell · 1 Hold · 1 did not vote", "Opus 5.5 vote", "Risk-on day", "shown only, does not vote",
                     "votes only in Strong + dollar", "Buy minus Sell over all six is +3"):
            self.assertIn(text, page)

    def test_today_says_when_the_decision_is_old_and_marks_a_strong_signal(self):
        page = self.client.get("/btc/").content.decode()
        self.assertIn("This is not today's advice", page)  # the decision is for July 1, long ago
        self.assertNotIn("badge-strong", page)  # 3 of 5 is a call but not a strong one
        Decision.objects.update(group_calls={"rules": "sell", "ml": "sell", "opus": "sell", "stress": "sell", "riskon": "hold"})
        page = self.client.get("/btc/").content.decode()
        for text in ("signal-sell", "Strong signal", "4 of the 5 voters say Sell", "Strong + dollar", "Sell votes lead Buy votes by 4 or more"):
            self.assertIn(text, page)
        with mock.patch("apps.backtest.services.daily_run_service.last_full_day", return_value=DAY):
            self.assertNotIn("This is not today's advice", self.client.get("/btc/").content.decode())

    def test_agents_link_opens_one_page_with_a_tab_per_agent(self):
        self.assertRedirects(self.client.get("/btc/agents/"), "/btc/agents/technical/")
        page = self.client.get("/btc/agents/riskon/?backtest=1").content.decode()
        for name in ("Technical analysis", "Derivatives", "Macro", "Financial stress", "Risk-on day"):
            self.assertIn(name, page)
        self.assertIn('href="/btc/agents/macro/?backtest=1"', page)  # tabs keep the live / backtest choice
        self.assertIn('href="/btc/agents/" aria-current="page">Agents</a>', page)  # the menu marks the page you are on
        self.assertNotIn('href="/btc/agents/macro/">Macro</a>', page)  # no longer one menu link per agent

    def test_agent_page_shows_both_scores_reasoning_and_chart_data(self):
        page = self.client.get("/btc/agents/technical/").content.decode()
        # The data table names its fields and rounds them; dates read "1 Jul 2026" on every page.
        for text in ("Opus 5.5 reasoning", "Price above 50-day average", "RSI (14 days)", "55.00", 'id="score-data"',
                     "Wed 1 Jul 2026", "Reads Bitcoin"):
            self.assertIn(text, page)
        self.assertNotIn("rsi_14", page)

    def test_agent_page_shows_a_day_once_and_only_the_kinds_the_agent_has(self):
        # The day was first run with rules only, then with the LLM: the LLM run is the one shown.
        AgentRun.objects.create(date=DAY, agent="technical", rule_score=50, direction="neutral", reasons=[], key_data={})
        from apps.dashboard.services import report_service
        history = report_service.agent_history("technical")
        self.assertEqual([(run.date, run.opus_score) for run in history], [(DAY, 71)])
        # The risk-on day has only a rules agent: no ML or LLM column, no prompt or cost.
        AgentRun.objects.create(date=DAY, agent="riskon", rule_score=40, direction="bearish", reasons=[],
                                key_data={"btc_change_1d_pct": 1.234, "rule_reasons": [], "skipped": []})
        page = self.client.get("/btc/agents/riskon/").content.decode()
        for text in ("Rules score", "Bitcoin today", "+1.23%", "score-chip vote-sell"):
            self.assertIn(text, page)
        for text in ("ML score", "Opus 5.5 score", "<th>Prompt</th>"):
            self.assertNotIn(text, page)

    def test_backtests_page_lists_runs_calibration_and_rule(self):
        BacktestRun.objects.create(name="rules:technical", start_date=DAY, end_date=DAY, trade_count=2,
                                   win_rate=50, total_profit_pct=3.5, max_drawdown_pct=1, buy_and_hold_pct=4,
                                   settings={"threshold": 60})
        BacktestRun.objects.create(name="rules:technical:calibration", start_date=DAY, end_date=DAY, settings={
            "score_type": "rules", "agent": "technical", "calls": 9, "brier_score": 0.3,
            "buckets": [{"label": "60s", "calls": 9, "hit_rate": 44.4, "avg_confidence": 61}]})
        period = {"calls": 120, "right": 66, "hit_rate": 55.0, "buy_days": 40, "trades": 9, "profit_pct": 12.5,
                  "drawdown_pct": 4.0, "hold_pct": 8.0}
        BacktestRun.objects.create(name="combining_rule", start_date=DAY, end_date=DAY, settings={
            "group_lead": 1, "overall": "all agree", "tuned_on": ["2019-01-01", "2024-12-31"],
            "tuning": period, "test": period})
        page = self.client.get("/btc/backtests/").content.decode()
        for text in ("Rules · Technical", "3.50%", "60s", "44%", "each vote among their domains", "all those votes agree", "55.0%"):
            self.assertIn(text, page)

    def test_costs_and_prompts_pages(self):
        page = self.client.get("/btc/costs/").content.decode()
        for text in ("$0.05", "Live daily runs", "1 day · $0.0500 per day", "Technical analysis"):
            self.assertIn(text, page)
        page = self.client.get("/btc/prompts/").content.decode()
        for text in ("You are the agent", "In use", "Technical analysis"):
            self.assertIn(text, page)

    def test_every_page_has_the_theme_button(self):
        self.assertContains(self.client.get("/btc/costs/"), "data-theme-toggle")


class FormatTests(TestCase):
    """How stored numbers are shown: named, rounded, in their unit. Display only."""

    def test_fields_get_a_name_and_a_unit(self):
        from apps.dashboard.templatetags.dashboard_format import field_label, field_value

        self.assertEqual(field_label("sma_200"), "200-day average")
        self.assertEqual(field_label("some_new_field_pct"), "Some new field")  # an unknown field still reads well
        self.assertEqual(field_value(73796.06, "close"), "$73,796")
        self.assertEqual(field_value(-11.9096, "change_30d_pct"), "-11.91%")
        self.assertEqual(field_value(3.9349, "cpi_yoy_pct"), "3.93%")
        self.assertEqual(field_value(5.8e-05, "funding_rate"), "0.0058%")
        self.assertEqual(field_value(0.7033, "long_account_ratio"), "70.3%")
        self.assertEqual(field_value(1, "fed_rate_change_60d"), "Hike")
        self.assertEqual(field_value(False, "near_support"), "No")
        self.assertEqual(field_value(None, "support"), "–")

    def test_ml_reasons_strategy_names_and_signs(self):
        from apps.dashboard.templatetags.dashboard_format import ml_reason, signed, strategy_name

        self.assertEqual(ml_reason("rsi_14 = 34.0068 points down (-0.10)"), "RSI (14 days) 34.01: ▼ pushes the score down")
        self.assertEqual(ml_reason("cpi_yoy_pct = 3.9349 (weight 19%)"), "Inflation (CPI, year on year) 3.93% (weight 19%)")
        self.assertEqual(ml_reason("Learned from 3351 past days"), "Learned from 3351 past days")
        self.assertEqual(strategy_name("rules:combining_rule"), "Rules · Combining rule")
        self.assertEqual((signed(3.14), signed(-2), signed(None)), ("+3.1", "-2.0", "–"))


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
                                    prompt_version=prompt, is_backtest=True, model="claude-opus-5-5")
        # A comparison run of another model never shows as Opus.
        AgentRun.objects.create(date=DAY, agent="macro", rule_score=50, opus_score=20, prompt_version=prompt,
                                is_backtest=True, model="claude-haiku-5-5")

    def test_judges_opus_calls_with_confidence_and_result(self):
        from apps.dashboard.services import signal_service

        table = signal_service.month_table(DAY)
        self.assertEqual(table["month"], DAY)
        calls = {row["date"]: row["calls"]["macro:opus"] for row in table["rows"]}
        buy, sell, hold = (calls[DAY + datetime.timedelta(days=n)] for n in range(3))
        self.assertEqual((buy.signal, buy.outcome, buy.confidence), ("buy", "wrong", 70))
        self.assertAlmostEqual(buy.result_pct, -5.0)  # 140 -> 133 seven days later
        self.assertEqual((sell.signal, sell.outcome, sell.confidence), ("sell", "right", 70))
        self.assertGreater(sell.result_pct, 0)  # the fall is a win for a Sell
        self.assertEqual(hold.outcome, "none")  # a Hold is never judged
        self.assertEqual(buy.note, "prompt v2")
        self.assertEqual(table["summary"]["macro:opus"], {"right": 1, "wrong": 1, "pending": 0, "hit_rate": 50.0})
        # Newest day first; the last days wait for their 7-day price.
        self.assertEqual(table["rows"][0]["calls"]["macro:opus"].outcome, "none")
        self.assertEqual(table["rows"][0]["date"], DAY + datetime.timedelta(days=14))

    def test_judge_and_pending(self):
        from apps.dashboard.services import signal_service

        self.assertEqual(signal_service.judge("buy", None), "pending")
        self.assertEqual(signal_service.judge("hold", 0.05), "none")
        self.assertEqual(signal_service.judge("sell", 0.05), "wrong")
        self.assertEqual(signal_service.score_call(20, None).confidence, 80)

    def test_month_page_shows_calls_results_and_filters(self):
        page = self.client.get("/btc/signals/?month=2026-07").content.decode()
        for text in ("call-wrong", "call-right", "▲ Buy", "▼ Sell", "70%", "lost -5.0%", "won +5.0%", "-5.00%",
                     "July 2026", "data-filter-source", "How to read this", "Overall", 'data-source="ml"'):
            self.assertIn(text, page)
        self.assertEqual(self.client.get("/btc/signals/?horizon=99&month=junk").status_code, 200)

    def test_strong_column_and_the_track_record(self):
        from apps.dashboard.services import report_service, signal_service

        self.assertEqual([column.key for column in signal_service.columns()[-2:]], ["strong", "strong_dollar"])
        page = self.client.get("/btc/signals/?month=2026-07").content.decode()
        for text in ("Strong (4 of 5)", "Strong + dollar"):
            self.assertIn(text, page)

        def row(day, vote, strong="hold", outcome="right", strong_dollar="hold"):
            calls = {"vote": signal_service.Call(vote, outcome=outcome), "strong": signal_service.Call(strong),
                     "strong_dollar": signal_service.Call(strong_dollar)}
            return {"date": DAY + datetime.timedelta(days=day), "return_pct": -3.0, "calls": calls}

        # Two Sell days are one trade, judged on its first day; a Hold ends it.
        rows = [row(0, "sell"), row(1, "sell", strong="sell", outcome="wrong"), row(2, "hold"), row(3, "buy", outcome="wrong"),
                row(4, "buy", outcome="pending", strong_dollar="buy")]
        found = report_service.trades(rows, "vote")
        self.assertEqual([(t["signal"], t["days"], t["strong"], t["strong_dollar"], t["outcome"]) for t in found],
                         [("sell", 2, True, False, "right"), ("buy", 2, False, True, "wrong")])
        record = report_service.record(rows, "vote")
        self.assertEqual((record["right"], record["trades"], record["hit_rate"], record["enough"]), (1, 2, 50.0, False))
        self.assertEqual(record["recent"][0]["signal"], "buy")  # newest first

    def test_today_and_agent_pages_show_the_record_and_the_price(self):
        AgentRun.objects.create(date=DAY, agent="macro", rule_score=40)
        Decision.objects.create(date=DAY, signal="no_trade", rule={"group_lead": 1},
                                group_calls={"rules": "sell", "ml": "hold", "opus": "sell", "stress": "sell", "riskon": "none"})
        page = self.client.get("/btc/").content.decode()
        for text in ("How its calls turned out", "Overall vote (3 of 5)", "Strong signal (4 of 5)", "Strong + dollar (lead of 4 among 6)", "Bitcoin close", "$126"):
            self.assertIn(text, page)  # the last stored close is 200 - 74
        page = self.client.get("/btc/agents/macro/").content.decode()
        for text in ("How often it was right", "Jan 2025 - Sep 2026"):
            self.assertIn(text, page)

    def test_overview_lists_periods_and_months(self):
        page = self.client.get("/btc/signals/overview/").content.decode()
        for text in ("Oct 2026 on", "Jul 2026", "?month=2026-07", "rate-cell"):
            self.assertIn(text, page)


class LLMLabelTests(TestCase):
    @override_settings(AI_MODEL="claude-haiku-5-5")
    def test_pages_name_the_model_in_use(self):
        from apps.dashboard.services import signal_service

        self.assertEqual(signal_service.sources()[2], ("opus", "Haiku 5.5"))
        self.assertIn("Haiku 5.5", self.client.get("/btc/signals/").content.decode())


class ProfitPageTests(TestCase):
    """Same falling prices: the LLM's Buy on DAY loses 140 -> 139; its Sell on DAY + 1 wins only when shorting."""

    setUp = SignalsPageTests.setUp

    def rows(self, short):
        from apps.dashboard.services import profit_service

        end = DAY + datetime.timedelta(days=5)
        page = profit_service.profit_page(start=DAY, end=end, short=short)
        self.assertEqual((page["preset"], page["start"], page["end"]), ("custom", DAY, end))
        return page, {row["key"]: row for row in page["rows"]}

    def test_profit_per_agent_against_holding(self):
        page, rows = self.rows(short=False)
        # 9 agents, stress ML, the risk-on day rules, dollar ML, 3 group votes, the overall vote, the two strong signals
        self.assertEqual(len(rows), 18)
        # One day long: a buy and a sell, 0.1% of the amount each.
        self.assertAlmostEqual(rows["macro:opus"]["profit_pct"], (139 / 140 * 0.999 ** 2 - 1) * 100, places=3)
        self.assertAlmostEqual(rows["macro:opus"]["before_fees_pct"], (139 / 140 - 1) * 100, places=3)
        self.assertEqual((rows["macro:opus"]["trades"], rows["macro:opus"]["days_long"]), (1, 1))
        self.assertLess(page["hold"].total_profit_pct, rows["macro:opus"]["profit_pct"])  # holding loses every day
        self.assertEqual(len(page["chart"]["lines"]), 18)

    def test_short_mode_profits_from_sell_calls(self):
        _, rows = self.rows(short=True)
        before_fees = (139 / 140) * (1 + (1 - 138 / 139))
        # In, out of the long and into the short, out: four fees.
        self.assertAlmostEqual(rows["macro:opus"]["profit_pct"], (before_fees * 0.999 ** 4 - 1) * 100, places=3)
        self.assertAlmostEqual(rows["macro:opus"]["before_fees_pct"], (before_fees - 1) * 100, places=3)
        self.assertEqual(rows["macro:opus"]["days_short"], 1)

    def test_calls_held_for_several_days_and_bitcoin_held_between_calls(self):
        from apps.dashboard.services.profit_service import positions

        signals = ["buy", "hold", "hold", "hold", "sell", "none", "hold"]
        self.assertEqual(positions(signals, short=False), [1, 0, 0, 0, 0, 0, 0])
        self.assertEqual(positions(signals, short=False, days=3), [1, 1, 1, 0, 0, 0, 0])
        self.assertEqual(positions(signals, short=True, days=3), [1, 1, 1, 0, -1, -1, -1])
        # A Sell-only agent kept in Bitcoin except on its Sell days.
        self.assertEqual(positions(signals, short=False, hold_between=True), [1, 1, 1, 1, 0, 1, 1])
        self.assertEqual(positions(["buy", "buy", "sell", "hold"], short=False, days=7), [1, 1, 0, 0])

    def test_page_links_keep_the_other_settings(self):
        page = self.client.get("/btc/profit/?period=2025&days=3&between=hold").content.decode()
        for text in ("Hold each call", "Between calls", "Hold Bitcoin", "3 days (a new Buy",
                     "?period=2025&amp;days=7&amp;between=hold", "?period=2025&amp;short=1&amp;days=3&amp;between=hold"):
            self.assertIn(text, page)
        self.assertEqual(self.client.get("/btc/profit/?days=5&between=junk").status_code, 200)

    def test_page_shows_filters_table_and_chart(self):
        page = self.client.get("/btc/profit/?start=2026-07-01&end=2026-07-06&short=1").content.decode()
        for text in ("data-filter-agent", "data-filter-source", "data-profit-table", "profit-chart-data",
                     "Go short", "Overall vote", "Macro", "Strong (4 of 5) signal", "Strong + dollar signal", "Before fees", "after fees"):
            self.assertIn(text, page)
        self.assertEqual(self.client.get("/btc/profit/?period=junk&start=bad").status_code, 200)


class AdviceButtonTests(TestCase):
    """The Today page button: runs the last full day only when it has not run, then shows the call."""

    def setUp(self):
        self.day = datetime.date(2026, 7, 2)
        patcher = mock.patch("apps.backtest.services.daily_run_service.last_full_day", return_value=self.day)
        patcher.start()
        self.addCleanup(patcher.stop)

    def save_decision(self, calls):
        AgentRun.objects.create(date=self.day, agent="technical", rule_score=60)
        Decision.objects.create(date=self.day, signal="no_trade", rule={"group_lead": 1}, group_calls=calls)

    def test_buy_when_three_of_five_say_buy(self):
        self.save_decision({"rules": "buy", "ml": "buy", "opus": "none", "stress": "buy", "riskon": "sell"})
        with mock.patch("apps.backtest.services.daily_run_service.run") as run:
            self.assertContains(self.client.post("/btc/advise/"), "BUY")
        run.assert_not_called()

    def test_sell_and_hold(self):
        self.save_decision({"rules": "sell", "ml": "sell", "opus": "none", "stress": "hold", "riskon": "sell"})
        self.assertContains(self.client.post("/btc/advise/"), "SELL")
        Decision.objects.update(group_calls={"rules": "sell", "ml": "sell", "opus": "none", "stress": "buy", "riskon": "none"})
        self.assertContains(self.client.post("/btc/advise/"), "HOLD: no clear call")

    def test_runs_the_day_when_it_has_not_run(self):
        with mock.patch("apps.backtest.services.daily_run_service.run",
                        side_effect=daily_run_service.DailyRunError("No BTC close yet")) as run:
            self.assertContains(self.client.post("/btc/advise/"), "No BTC close yet")
        run.assert_called_once_with(self.day, collect=True)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get("/btc/advise/").status_code, 405)
