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
# A "strong signal": this many of the five agree. It is shown beside the vote and changes no
# call. From 2025 to Nov 2026 it was right in 9 of 10 trades (8 of 13 on 2019-24): too few to prove.
STRONG_NEEDED = 4
# A second strong signal, shown beside the first so new data can decide between them: the five
# voters plus one that votes nowhere else, the dollar ML agent, and Buy votes minus Sell votes
# of the six at least STRONG_NET (so an opposing vote counts against it). Chosen on 2019-2024
# among 17 ways to count (Nov 11 2026): 36 of 52 trades right there, 10 of 13 from 2025, which
# missed the 80% set beforehand. See CLAUDE.md, "Strong signal with the dollar agent".
STRONG_ONLY = {"dollar": ("ml", "dollar")}
STRONG_VOTERS = VOTERS_ROUND_2 + list(STRONG_ONLY)
STRONG_NET = 4


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
    """Every voter's call: round 1, the solo voters and the strong signal's own voter:
    {"rules": "buy", "ml": "hold", "opus": "none", "stress": "buy", "riskon": "sell", "dollar": "buy"}
    from {source: {agent: score}}."""
    calls = {source: group_call(voters(source, scores_by_source.get(source, {})), group_lead) for source in GROUPS}
    for voter, (source, agent) in {**SOLO, **STRONG_ONLY}.items():
        calls[voter] = solo_call(scores_by_source.get(source, {}).get(agent))
    return calls


def round_2(groups):
    """The five voters of the overall vote; a voter missing from a saved Decision did not vote."""
    return {voter: groups.get(voter, "none") for voter in VOTERS_ROUND_2}


def overall_net(groups):
    return sum(CALL_VOTES[signal] for signal in round_2(groups).values())


def agreed_call(groups, needed):
    """Buy or Sell when at least `needed` voters say it; "none" when none voted."""
    voted = [signal for signal in groups.values() if signal != "none"]
    if not voted:
        return "none"
    for side in ("buy", "sell"):
        if voted.count(side) >= needed:
            return side
    return "hold"


def overall_call(groups):
    """Round 2: Buy or Sell when at least OVERALL_NEEDED of the five voters say it. The dollar
    agent is in `groups` but has no vote here."""
    return agreed_call(round_2(groups), OVERALL_NEEDED)


def strong_call(groups):
    """The overall call on the days at least STRONG_NEEDED of the five voters back it, else Hold."""
    return agreed_call(round_2(groups), STRONG_NEEDED)


def strong_net(groups):
    """Buy votes minus Sell votes of the six voters of the strong signal with the dollar."""
    return sum(CALL_VOTES[groups.get(voter, "none")] for voter in STRONG_VOTERS)


def strong_dollar_call(groups):
    """Buy or Sell on the days the six voters lean that way by at least STRONG_NET, else Hold.
    Four of six in favor then means at least three of the overall vote's five, so it never
    contradicts the overall vote."""
    if all(groups.get(voter, "none") == "none" for voter in STRONG_VOTERS):
        return "none"
    net = strong_net(groups)
    if net >= STRONG_NET:
        return "buy"
    if net <= -STRONG_NET:
        return "sell"
    return "hold"


def decide(scores_by_source, rule):
    """(every voter's call, overall call) for one day under {"group_lead": g}."""
    groups = group_calls(scores_by_source, rule["group_lead"])
    return groups, overall_call(groups)
