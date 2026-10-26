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


def candidate(group_lead, overall_lead, hit_rate, calls):
    return cs.Candidate(group_lead, overall_lead, result(hit_rate, calls), result(50, 10))


class VoteTests(SimpleTestCase):
    def test_each_agent_votes_buy_sell_or_hold(self):
        scores = {"a": 70, "b": 55, "c": 45, "d": 50, "e": None}
        self.assertEqual(net_votes(scores), 1)  # two Buy, one Sell, a Hold and a missing score

    def test_the_lead_decides(self):
        scores = {"a": 70, "b": 60, "c": 30}
        self.assertEqual((call(scores, 1), call(scores, 2)), ("buy", "hold"))
        self.assertEqual(call({"a": 20, "b": 30}, 2), "sell")

    def test_each_kind_of_agent_votes_among_its_domains(self):
        scores = {"rules": {"technical": 60, "derivatives": 70, "macro": 30},
                  "ml": {"technical": 50, "derivatives": 40, "macro": 50},
                  "opus": {"technical": None, "derivatives": None, "macro": None}}
        self.assertEqual(group_calls(scores, 1), {"rules": "buy", "ml": "sell", "opus": "none"})
        self.assertEqual(group_calls(scores, 2), {"rules": "hold", "ml": "hold", "opus": "none"})

    def test_the_group_votes_vote_and_a_missing_group_abstains(self):
        self.assertEqual(overall_call({"rules": "buy", "ml": "buy", "opus": "sell"}, 1), "buy")
        self.assertEqual(overall_call({"rules": "buy", "ml": "hold", "opus": "none"}, 2), "hold")
        self.assertEqual(overall_call({"rules": "sell", "ml": "sell", "opus": "none"}, 2), "sell")
        self.assertEqual(overall_call({"rules": "none", "ml": "none", "opus": "none"}, 1), "none")

    def test_decide_runs_both_rounds(self):
        scores = {"rules": {"technical": 70, "derivatives": 60}, "ml": {"macro": 56}}
        groups, signal = decide(scores, {"group_lead": 1, "overall_lead": 2})
        self.assertEqual((groups, signal), ({"rules": "buy", "ml": "buy", "opus": "none"}, "buy"))


class BestVoteTests(SimpleTestCase):
    def test_highest_hit_rate_with_enough_calls(self):
        lucky = candidate(3, 2, hit_rate=80, calls=20)
        steady = candidate(1, 2, hit_rate=56, calls=400)
        loose = candidate(1, 1, hit_rate=53, calls=900)
        self.assertIs(cs.best([lucky, steady, loose]), steady)

    def test_none_when_no_vote_calls_enough(self):
        self.assertIsNone(cs.best([candidate(3, 2, hit_rate=90, calls=cs.MIN_CALLS - 1)]))


class ChooseAndDecideTests(TestCase):
    def setUp(self):
        # The price rises after even days and falls after odd days, from 2019 into 2025.
        start = datetime.date(2024, 6, 1)
        self.days = [start + datetime.timedelta(days=i) for i in range(400)]
        closes = [Point(d, "close", 100.0 if i % 2 == 0 else 105.0) for i, d in enumerate(self.days)]
        market_data_repository.save_points("binance", closes)
        self.market = backtest_service.load_market(self.days[0], self.days[-1])
        # Rules are right every day (two domains agree, macro holds); ML always says Buy.
        self.rules = {d: {"technical": 70 if i % 2 == 0 else 30, "derivatives": 70 if i % 2 == 0 else 30,
                          "macro": 50} for i, d in enumerate(self.days)}
        self.ml = {d: {"technical": 60, "derivatives": 60, "macro": 60} for d in self.days}

    def returns_7d(self):
        from apps.backtest.calibration import forward_returns
        from apps.backtest.repositories import price_repository

        return forward_returns(self.market.days, price_repository.closes(self.days[0], self.days[-1]))

    def test_chosen_on_the_tuning_years_and_reported_on_the_test(self):
        found, chosen = cs.choose({"rules": self.rules, "ml": self.ml}, self.market, self.returns_7d(), self.days[-1])
        self.assertEqual(len(found), len(cs.GROUP_LEADS) * len(cs.OVERALL_LEADS))
        # 7 days on, the price is where it was a day later: rules' even-day Buys rise. On odd
        # days the rules' Sell and ML's Buy cancel to Hold, so every call made is right.
        self.assertEqual((chosen.group_lead, chosen.overall_lead), (1, 1))
        self.assertEqual(chosen.tuning.hit_rate, 100)
        saved = BacktestRun.objects.get(name=cs.RULE_NAME)
        self.assertEqual(saved.settings["tuned_on"], ["2019-01-01", "2024-12-31"])
        self.assertEqual(saved.start_date, cs.TEST_START)
        self.assertGreater(saved.settings["test"]["calls"], 0)
        self.assertEqual(cs.current_rule(), chosen.rule)

    def test_default_rule_until_one_is_chosen(self):
        self.assertEqual(cs.current_rule(), cs.DEFAULT_RULE)
        # A choice saved by the old one-round vote does not carry over.
        BacktestRun.objects.create(name=cs.RULE_NAME, start_date=self.days[0], end_date=self.days[0],
                                   settings={"sources": ["rules", "ml"], "min_net_votes": 2})
        self.assertEqual(cs.current_rule(), cs.DEFAULT_RULE)

    def test_decision_applies_the_vote_to_live_runs(self):
        day = datetime.date(2026, 7, 3)
        for agent, rules, ml in (("technical", 72, 60), ("derivatives", 66, 50), ("macro", 40, 40)):
            AgentRun.objects.create(date=day, agent=agent, rule_score=rules, ml_score=ml)
        AgentRun.objects.create(date=day, agent="macro", rule_score=90, is_backtest=True)  # backtests never count

        # Default, both leads 1. Rules: 2 Buy, 1 Sell -> Buy. ML: 1 Buy, 1 Hold, 1 Sell -> Hold.
        decision = decision_service.make_decision(day)
        self.assertEqual(decision.group_calls, {"rules": "buy", "ml": "hold", "opus": "none"})
        self.assertEqual((decision.signal, decision.net_votes), (Decision.Signal.BUY, 1))
        self.assertEqual((decision.technical_score, decision.macro_score), (72, 40))

        BacktestRun.objects.create(name=cs.RULE_NAME, start_date=day, end_date=day,
                                   settings={"group_lead": 1, "overall_lead": 2})
        decision = decision_service.make_decision(day)  # only the Rules vote says Buy: not enough
        self.assertEqual((decision.signal, decision.net_votes), (Decision.Signal.NO_TRADE, 1))
        self.assertEqual(decision.rule, {"group_lead": 1, "overall_lead": 2})
