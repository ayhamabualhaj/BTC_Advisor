import datetime

from django.test import SimpleTestCase, TestCase

from apps.agents.models import AgentRun
from apps.backtest.decision_rule import call, decide, group_calls, net_votes, overall_call
from apps.backtest.models import BacktestRun, Decision
from apps.backtest.services import backtest_service, combining_service as cs, decision_service
from apps.data.collectors.base import Point
from apps.data.repositories import market_data_repository


def result(hit_rate, calls):
    return cs.Result(calls, round(calls * hit_rate / 100), hit_rate, 0, 0, 0.0, 0.0, 0.0)


def candidate(group_lead, hit_rate, calls):
    return cs.Candidate(group_lead, result(hit_rate, calls), result(50, 10))


class VoteTests(SimpleTestCase):
    def test_each_agent_votes_buy_sell_or_hold(self):
        scores = {"a": 70, "b": 55, "c": 45, "d": 50, "e": None}
        self.assertEqual(net_votes(scores), 1)  # two Buy, one Sell, a Hold and a missing score

    def test_the_lead_decides(self):
        scores = {"a": 70, "b": 60, "c": 30}
        self.assertEqual((call(scores, 1), call(scores, 2)), ("buy", "hold"))
        self.assertEqual(call({"a": 20, "b": 30}, 2), "sell")

    def test_each_kind_of_agent_votes_among_its_domains(self):
        # Stress and the risk-on day vote on their own, never inside the ML or Rules vote.
        scores = {"rules": {"technical": 60, "derivatives": 70, "macro": 30, "riskon": 40},
                  "ml": {"macro": 50, "stress": 40},
                  "opus": {"technical": None, "derivatives": None, "macro": None}}
        self.assertEqual(group_calls(scores, 1),
                         {"rules": "buy", "ml": "hold", "opus": "none", "stress": "sell", "riskon": "sell"})
        self.assertEqual(group_calls(scores, 2),
                         {"rules": "hold", "ml": "hold", "opus": "none", "stress": "sell", "riskon": "sell"})

    def test_technical_and_derivatives_ml_do_not_vote(self):
        scores = {"rules": {}, "ml": {"technical": 70, "derivatives": 70, "macro": 50}}
        self.assertEqual(group_calls(scores, 1)["ml"], "hold")

    def test_overall_calls_when_three_of_five_agree(self):
        def calls(rules, ml, opus, stress, riskon):
            return {"rules": rules, "ml": ml, "opus": opus, "stress": stress, "riskon": riskon}

        self.assertEqual(overall_call(calls("buy", "buy", "buy", "sell", "sell")), "buy")
        self.assertEqual(overall_call(calls("sell", "hold", "sell", "buy", "sell")), "sell")
        self.assertEqual(overall_call(calls("buy", "buy", "hold", "sell", "hold")), "hold")
        # A voter without a score does not vote, which counts as not agreeing.
        self.assertEqual(overall_call(calls("buy", "buy", "none", "buy", "none")), "buy")
        self.assertEqual(overall_call(calls("buy", "buy", "none", "none", "none")), "hold")
        self.assertEqual(overall_call(calls("none", "none", "none", "none", "none")), "none")

    def test_decide_runs_both_rounds(self):
        scores = {"rules": {"technical": 70, "derivatives": 60}, "ml": {"macro": 56, "stress": 60}}
        groups, signal = decide(scores, {"group_lead": 1, "overall": cs.OVERALL})
        self.assertEqual(groups, {"rules": "buy", "ml": "buy", "opus": "none", "stress": "buy", "riskon": "none"})
        self.assertEqual(signal, "buy")


class BestVoteTests(SimpleTestCase):
    def test_highest_hit_rate_with_enough_calls(self):
        lucky = candidate(3, hit_rate=80, calls=20)
        steady = candidate(2, hit_rate=56, calls=400)
        loose = candidate(1, hit_rate=53, calls=900)
        self.assertIs(cs.best([lucky, steady, loose]), steady)

    def test_none_when_no_vote_calls_enough(self):
        self.assertIsNone(cs.best([candidate(3, hit_rate=90, calls=cs.MIN_CALLS - 1)]))


class ChooseAndDecideTests(TestCase):
    def setUp(self):
        # The price rises after even days and falls after odd days, from 2019 into 2025.
        start = datetime.date(2024, 6, 1)
        self.days = [start + datetime.timedelta(days=i) for i in range(400)]
        closes = [Point(d, "close", 100.0 if i % 2 == 0 else 105.0) for i, d in enumerate(self.days)]
        market_data_repository.save_points("binance", closes)
        self.market = backtest_service.load_market(self.days[0], self.days[-1])
        # Rules are right every day (two domains agree, macro holds); macro and stress ML always say Buy.
        self.rules = {d: {"technical": 70 if i % 2 == 0 else 30, "derivatives": 70 if i % 2 == 0 else 30,
                          "macro": 50} for i, d in enumerate(self.days)}
        self.ml = {d: {"technical": 60, "derivatives": 60, "macro": 60, "stress": 60} for d in self.days}

    def returns_7d(self):
        from apps.backtest.calibration import forward_returns
        from apps.backtest.repositories import price_repository

        return forward_returns(self.market.days, price_repository.closes(self.days[0], self.days[-1]))

    def test_chosen_on_the_tuning_years_and_reported_on_the_test(self):
        found, chosen = cs.choose({"rules": self.rules, "ml": self.ml}, self.market, self.returns_7d(), self.days[-1])
        self.assertEqual(len(found), len(cs.GROUP_LEADS))
        # 7 days on, the price is where it was a day later: rules' even-day Buys rise and ML and
        # stress agree (3 of 5). On odd days the rules sell and the other two buy: Hold. Every call is right.
        self.assertEqual(chosen.group_lead, 1)
        self.assertEqual(chosen.tuning.hit_rate, 100)
        saved = BacktestRun.objects.get(name=cs.RULE_NAME)
        self.assertEqual(saved.settings["tuned_on"], ["2019-01-01", "2024-12-31"])
        self.assertEqual(saved.start_date, cs.TEST_START)
        self.assertGreater(saved.settings["test"]["calls"], 0)
        self.assertEqual(cs.current_rule(), chosen.rule)

    def test_default_rule_until_one_is_chosen(self):
        self.assertEqual(cs.current_rule(), cs.DEFAULT_RULE)
        # Choices saved by older votes do not carry over.
        for old in ({"sources": ["rules", "ml"], "min_net_votes": 2}, {"group_lead": 3, "overall_lead": 1}):
            BacktestRun.objects.create(name=cs.RULE_NAME, start_date=self.days[0], end_date=self.days[0], settings=old)
            self.assertEqual(cs.current_rule(), cs.DEFAULT_RULE)

    def test_decision_applies_the_vote_to_live_runs(self):
        day = datetime.date(2026, 7, 3)
        for agent, rules, ml in (("technical", 72, 60), ("derivatives", 66, 50), ("macro", 40, 50),
                                 ("stress", None, 60), ("riskon", 40, None)):
            AgentRun.objects.create(date=day, agent=agent, rule_score=rules, ml_score=ml)
        AgentRun.objects.create(date=day, agent="macro", rule_score=90, is_backtest=True)  # backtests never count

        # Default, group lead 1. Rules: 2 Buy, 1 Sell -> Buy (the risk-on day votes on its own: Sell).
        decision = decision_service.make_decision(day)
        # ML: only macro votes (technical's 60 Buy does not count): 50 Hold -> Hold. Stress Buy.
        # Two Buys of five: no call.
        self.assertEqual(decision.group_calls,
                         {"rules": "buy", "ml": "hold", "opus": "none", "stress": "buy", "riskon": "sell"})
        self.assertEqual((decision.signal, decision.net_votes), (Decision.Signal.NO_TRADE, 1))
        self.assertEqual((decision.technical_score, decision.macro_score), (72, 40))

        AgentRun.objects.filter(agent="macro").update(ml_score=60)  # ML now macro Buy -> 3 Buys
        decision = decision_service.make_decision(day)
        self.assertEqual((decision.signal, decision.net_votes), (Decision.Signal.BUY, 2))
        self.assertEqual(decision.rule, cs.DEFAULT_RULE)
