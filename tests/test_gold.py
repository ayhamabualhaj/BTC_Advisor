"""Gold beside Bitcoin: its own prices, agents, vote, outcomes on trading days, and pages."""

import datetime
import io

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from ai import domains, gold, gold_dollar, gold_stress, gold_technical, ml, prompts
from apps.agents.models import AgentRun, MemoryCase
from apps.agents.services import memory_service
from apps.backtest import decision_rule
from apps.backtest.calibration import forward_returns, later_close
from apps.backtest.models import Decision, Outcome
from apps.backtest.repositories import price_repository
from apps.backtest.services import backtest_service, combining_service, decision_service, outcome_service, score_store
from apps.data import assets
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository

FRIDAY = datetime.date(2026, 7, 3)
MONDAY = FRIDAY + datetime.timedelta(days=3)


def D(days):
    return FRIDAY + datetime.timedelta(days=days)


def save_gold(closes):
    """{date: close} as gold candles."""
    market_data_repository.save_points("yahoo", [Point(day, f"gold_{field}", value)
                                                 for day, value in closes.items() for field in ("close", "high", "low")])


class AssetTests(SimpleTestCase):
    def test_bitcoin_unless_inside_use(self):
        self.assertEqual(assets.current().key, "btc")
        with assets.use("gold") as asset:
            self.assertEqual((assets.current().key, asset.label), ("gold", "Gold"))
            self.assertEqual(domains.agents(), ["gold_technical", "gold_macro", "gold_stress", "gold_dollar"])
        self.assertEqual(assets.current().key, "btc")
        self.assertEqual(domains.agents()[0], "technical")

    def test_names_and_domains(self):
        gold_asset = assets.ASSETS["gold"]
        self.assertEqual(assets.of_agent("gold_macro"), gold_asset)
        self.assertEqual(assets.of_agent("macro").key, "btc")
        self.assertEqual(gold_asset.domain("gold_macro"), "macro")
        self.assertEqual((gold_asset.named("combining_rule"), assets.ASSETS["btc"].named("combining_rule")),
                         ("gold:combining_rule", "combining_rule"))

    def test_gold_agents_have_the_kinds_the_study_kept(self):
        kinds = {agent: [kind for kind in ("rules", "ml", "opus") if domains.has(agent, kind)]
                 for agent in assets.ASSETS["gold"].agents}
        self.assertEqual(kinds, {"gold_technical": ["rules", "ml", "opus"], "gold_macro": ["ml", "opus"],
                                 "gold_stress": ["rules", "ml"], "gold_dollar": ["rules", "ml"]})

    def test_scores_are_fingerprinted_per_asset(self):
        with assets.use("gold"):
            gold_print = score_store.fingerprint()
        self.assertNotEqual(gold_print, score_store.fingerprint())

    def test_gold_prompts_state_golds_own_usual_rate(self):
        text = prompts.prompt_text(gold_technical.opus.PROMPT_FILE)
        self.assertIn("2005-2019", text)
        self.assertNotIn("2017-2024", text)
        self.assertNotIn("gold", text.lower())  # the asset stays unnamed


class GoldRuleTests(SimpleTestCase):
    def test_each_rule_buys_its_dip_and_never_sells(self):
        cases = ((gold_technical.rules, "rsi_14", 41, 60), (gold_technical.rules, "rsi_14", 75, 50),
                 (gold_stress.rules, "vix", 25, 60), (gold_stress.rules, "vix", 12, 50),
                 (gold_dollar.rules, "gold_minus_dxy_20d_pct", -4.0, 60), (gold_dollar.rules, "gold_minus_dxy_20d_pct", 6.0, 50))
        for rules, key, value, score in cases:
            self.assertEqual(rules.score({key: value}).score, score, (key, value))
        self.assertEqual(gold_technical.rules.score({"rsi_14": None}).skipped, ["RSI"])

    def test_models_wait_for_outcomes_that_come_after_a_weekend(self):
        day = datetime.date(2026, 7, 15)
        self.assertEqual(gold.training_cutoff(day), ml.monthly_cutoff(day) - datetime.timedelta(days=4))


class GoldVoteTests(SimpleTestCase):
    def decide(self, technical, stress, dollar):
        scores = {"rules": {"gold_technical": technical, "gold_stress": stress, "gold_dollar": dollar},
                  "ml": {"gold_macro": 30}, "opus": {"gold_technical": 30, "gold_macro": 30}}
        with assets.use("gold"):
            groups, overall = decision_rule.decide(scores, combining_service.current_rule())
            return overall, decision_rule.strong_call(groups), decision_rule.strong_dollar_call(groups)

    def test_buy_when_two_of_the_three_rules_agree(self):
        # The ML and LLM agents say Sell here, and do not count.
        self.assertEqual(self.decide(60, 60, 50), ("buy", "hold", "none"))
        self.assertEqual(self.decide(60, 50, 50), ("hold", "hold", "none"))
        self.assertEqual(self.decide(60, 60, 60), ("buy", "buy", "none"))

    def test_bitcoins_vote_is_untouched(self):
        self.assertEqual(decision_rule.current(), decision_rule.BITCOIN)
        self.assertEqual(decision_rule.current().round_2, ["rules", "ml", "opus", "stress", "riskon"])
        with assets.use("gold"):
            self.assertEqual(decision_rule.current().round_2, ["gold_technical", "gold_stress", "gold_dollar"])
            self.assertIn("2 of the 3 agree", combining_service.describe(combining_service.current_rule()))


class TradingDayTests(SimpleTestCase):
    def test_the_outcome_is_the_first_close_on_or_after_the_day(self):
        closes = {FRIDAY: 100.0, MONDAY: 110.0}
        self.assertIsNone(later_close(closes, FRIDAY, 1))             # Bitcoin's rule: that exact day
        self.assertEqual(later_close(closes, FRIDAY, 1, wait=4), 110.0)
        self.assertEqual(forward_returns([FRIDAY], closes, 1), {})
        self.assertAlmostEqual(forward_returns([FRIDAY], closes, 1, wait=4)[FRIDAY], 0.10)
        self.assertIsNone(later_close(closes, FRIDAY, 7, wait=4))     # not known yet


class GoldDataTests(TestCase):
    def setUp(self):
        # Three weeks of weekdays: 100, 101, ...
        days = [D(n) for n in range(-14, 11) if D(n).weekday() < 5]
        self.closes = {day: 100.0 + i for i, day in enumerate(days)}
        save_gold(self.closes)
        market_data_repository.save_points("binance", [Point(FRIDAY, "close", 50000.0)])

    def test_prices_follow_the_asset(self):
        self.assertEqual(price_repository.closes(FRIDAY, MONDAY), {FRIDAY: 50000.0})
        with assets.use("gold"):
            self.assertEqual(sorted(price_repository.closes(FRIDAY, MONDAY)), [FRIDAY, MONDAY])
            self.assertEqual(price_repository.latest_close_date(), max(self.closes))

    def test_a_fridays_return_runs_to_monday(self):
        with assets.use("gold"):
            market = backtest_service.load_market(FRIDAY, MONDAY)
        self.assertEqual(market.days, [FRIDAY, MONDAY])
        self.assertAlmostEqual(market.next_day_returns[0], self.closes[MONDAY] / self.closes[FRIDAY] - 1)

    def test_memory_takes_the_first_close_a_week_later(self):
        saturday = FRIDAY + datetime.timedelta(days=1)
        save_gold({saturday: 100.0})  # an odd Saturday session: a week later is a Saturday, so Monday's close counts
        saved = memory_service.build_cases("gold_dollar", gold_dollar.inputs.model_input, saturday, saturday)
        case = MemoryCase.objects.get(agent="gold_dollar")
        monday_after = saturday + datetime.timedelta(days=9)
        self.assertEqual(saved, 1)
        self.assertAlmostEqual(case.return_7d_pct, round((self.closes[monday_after] / 100.0 - 1) * 100, 2))
        # ... and may only be learned from once that close can be known.
        self.assertEqual(memory_service.outcome_known_cutoff("gold_dollar", D(20)), D(20 - 11))
        self.assertEqual(memory_service.outcome_known_cutoff("dollar", D(20)), D(20 - 7))

    def test_decisions_and_outcomes_are_kept_per_asset(self):
        AgentRun.objects.create(date=FRIDAY, agent="technical", rule_score=60)
        for agent, score in (("gold_technical", 60), ("gold_stress", 60), ("gold_dollar", 50), ("gold_macro", None)):
            AgentRun.objects.create(date=FRIDAY, agent=agent, rule_score=score, ml_score=70)
        with assets.use("gold"):
            decision = decision_service.make_decision(FRIDAY)
            outcome_service.update_outcomes()
        self.assertEqual((decision.asset, decision.signal, decision.technical_score), ("gold", "buy", 60))
        self.assertEqual(decision.group_calls["gold_technical"], "buy")
        outcome_service.update_outcomes()
        gold_outcome, btc_outcome = Outcome.objects.get(asset="gold"), Outcome.objects.get(asset="btc")
        self.assertEqual((gold_outcome.price_at_decision, btc_outcome.price_at_decision), (self.closes[FRIDAY], 50000.0))
        # Friday's 1-day price is Monday's close; gold rose over the week, and its technical rule said Buy.
        self.assertEqual(gold_outcome.price_after_1d, self.closes[MONDAY])
        self.assertTrue(gold_outcome.technical_correct)
        self.assertEqual(Decision.objects.filter(asset="btc").count(), 0)

    def test_the_daily_run_skips_gold_when_its_market_was_closed(self):
        out = io.StringIO()
        saturday = FRIDAY + datetime.timedelta(days=1)
        call_command("daily_run", "--asset", "gold", "--date", saturday.isoformat(), "--no-collect", "--rules-only", stdout=out)
        self.assertIn("the market was closed", out.getvalue())
        self.assertFalse(AgentRun.objects.exists())


class GoldPagesTests(TestCase):
    def test_the_first_page_offers_both_markets(self):
        page = self.client.get("/").content.decode()
        for text in ("Which market?", 'href="/btc/"', 'href="/gold/"', "Bitcoin", "Gold"):
            self.assertIn(text, page)

    def test_gold_pages_work_with_an_empty_database(self):
        for url in ("/gold/", "/gold/agents/gold_macro/", "/gold/signals/", "/gold/signals/overview/", "/gold/backtests/",
                    "/gold/costs/", "/gold/prompts/", "/gold/profit/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertRedirects(self.client.get("/gold/agents/"), "/gold/agents/gold_technical/")
        self.assertRedirects(self.client.get("/gold/models/"), "/btc/models/")

    def test_markets_do_not_share_agents_or_urls(self):
        self.assertEqual(self.client.get("/silver/").status_code, 404)
        self.assertEqual(self.client.get("/gold/agents/technical/").status_code, 404)
        self.assertEqual(self.client.get("/btc/agents/gold_technical/").status_code, 404)

    def test_gold_today_shows_its_own_vote_and_price(self):
        days = [D(n) for n in range(-30, 1) if D(n).weekday() < 5]
        save_gold({day: 4000.0 + i for i, day in enumerate(days)})
        for agent, score in (("gold_technical", 60), ("gold_stress", 60), ("gold_dollar", 50)):
            AgentRun.objects.create(date=FRIDAY, agent=agent, rule_score=score, ml_score=58, key_data={"rsi_14": 40.0})
        AgentRun.objects.create(date=FRIDAY, agent="gold_macro", ml_score=44)
        with assets.use("gold"):
            decision_service.make_decision(FRIDAY)
        page = self.client.get("/gold/").content.decode()
        for text in ("Gold close", "2 of 3 must agree", "2 of the 3 voters say Buy", "Technical analysis rules",
                     "shown only, does not vote", "Gold and the vote", 'href="/gold/signals/"'):
            self.assertIn(text, page)
        self.assertNotIn("Strong + dollar", page)
        # Bitcoin's page knows nothing of it.
        self.assertContains(self.client.get("/btc/"), "No agent runs")
        signals = self.client.get(f"/gold/signals/?month={FRIDAY:%Y-%m}").content.decode()
        self.assertIn("Gold after 7d", signals)
        self.assertNotIn("Derivatives", signals)
