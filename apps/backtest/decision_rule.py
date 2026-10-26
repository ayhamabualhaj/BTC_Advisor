"""The combining rule: a vote in two rounds.

Round 1: each kind of agent votes among its domains. The technical, derivatives and macro
rule agents give the Rules vote, the macro ML agent the ML vote (see VOTERS), the LLM agents
the LLM vote. An agent without a score abstains. Each agent says Buy (score >= 55), Sell
(<= 45) or Hold; the group says Buy when its Buy votes lead its Sell votes by at least
`group_lead`, Sell when the reverse.

Round 2, the overall vote, has five voters: those three group votes plus two agents that
vote on their own (SOLO): the financial stress ML agent and the risk-on day rule. Buy (or
Sell) when at least OVERALL_NEEDED of the five say it. A voter with no score (the LLM before
2025) does not vote, which counts as not agreeing, as a Hold does. The risk-on day never
says Buy; without a Nasdaq move (weekends, US holidays) it says Hold. The group
lead is chosen on 2019-2024 by choose_combining_rule. The system only advises buying: a
Sell means stay out.
"""

from ai.scoring import BEARISH_AT, BULLISH_AT

GROUPS = ["rules", "ml", "opus"]
# Agents that vote in round 2 on their own: {voter: (kind of score, agent)}. Neither is in a
# group as well, so no score counts twice.
SOLO = {"stress": ("ml", "stress"), "riskon": ("rules", "riskon")}
VOTERS_ROUND_2 = GROUPS + list(SOLO)
# Who votes in a group (a group not listed: every domain). Technical and derivatives ML are
# still scored and shown but do not vote: ~98% of their calls were Buys and they were right
# less often than "always up" (Oct 2026). Stress and the risk-on day vote on their own.
VOTERS = {"rules": {"technical", "derivatives", "macro"}, "ml": {"macro"}}
CALL_VOTES = {"buy": 1, "sell": -1, "hold": 0, "none": 0}
# Round 2: how many of the five voters must say the same thing.
OVERALL_NEEDED = 3


def vote(score):
    if score is None:
        return 0
    if score >= BULLISH_AT:
        return 1
    if score <= BEARISH_AT:
        return -1
    return 0


def net_votes(scores):
    """Buy votes minus Sell votes over {voter: score}; a missing score abstains."""
    return sum(vote(score) for score in scores.values())


def call(scores, min_net_votes):
    net = net_votes(scores)
    if net >= min_net_votes:
        return "buy"
    if net <= -min_net_votes:
        return "sell"
    return "hold"


def is_buy(scores, min_net_votes):
    return call(scores, min_net_votes) == "buy"


def group_call(scores, group_lead):
    """One kind of agent's vote over {agent: score}; "none" when no agent has a score."""
    if not any(score is not None for score in scores.values()):
        return "none"
    return call(scores, group_lead)


def voters(source, scores):
    """The {agent: score} of a group's agents that vote."""
    allowed = VOTERS.get(source)
    return scores if allowed is None else {agent: score for agent, score in scores.items() if agent in allowed}


def solo_call(score):
    """One agent voting on its own: its own Buy / Sell / Hold, "none" without a score."""
    if score is None:
        return "none"
    return {1: "buy", -1: "sell", 0: "hold"}[vote(score)]


def group_calls(scores_by_source, group_lead):
    """Round 1 plus the solo voters: {"rules": "buy", "ml": "hold", "opus": "none", "stress": "buy",
    "riskon": "sell"} from {source: {agent: score}}."""
    calls = {source: group_call(voters(source, scores_by_source.get(source, {})), group_lead) for source in GROUPS}
    for voter, (source, agent) in SOLO.items():
        calls[voter] = solo_call(scores_by_source.get(source, {}).get(agent))
    return calls


def overall_net(groups):
    return sum(CALL_VOTES[signal] for signal in groups.values())


def overall_call(groups):
    """Round 2: Buy or Sell when at least OVERALL_NEEDED voters say it; "none" when none voted."""
    voted = [signal for signal in groups.values() if signal != "none"]
    if not voted:
        return "none"
    for side in ("buy", "sell"):
        if voted.count(side) >= OVERALL_NEEDED:
            return side
    return "hold"


def decide(scores_by_source, rule):
    """(group calls, overall call) for one day under {"group_lead": g}."""
    groups = group_calls(scores_by_source, rule["group_lead"])
    return groups, overall_call(groups)
