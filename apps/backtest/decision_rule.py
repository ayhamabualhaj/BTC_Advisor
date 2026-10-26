"""The combining rule: a vote in two rounds.

Round 1: each kind of agent votes among its domains. The rule agents (technical,
derivatives, macro) give the Rules vote, the macro and financial stress ML agents the ML
vote (see VOTERS), the Opus agents the Opus vote. An agent without a score abstains. Each agent says Buy (score >= 55), Sell (<= 45) or Hold; the group says Buy when
its Buy votes lead its Sell votes by at least `group_lead`, Sell when the reverse.

Round 2, the overall vote: Buy (or Sell) only when every group vote agrees. A group with
no scores (Opus before mid-2026) sits out, but at least MIN_GROUPS must have voted. The
group lead is chosen on 2019-2024 by choose_combining_rule. The system only advises
buying: a Sell means stay out.
"""

from ai.scoring import BEARISH_AT, BULLISH_AT

GROUPS = ["rules", "ml", "opus"]
# Who votes in a group (a group not listed: every domain). Technical and derivatives ML are
# still scored and shown but do not vote: ~98% of their calls were Buys and they were right
# less often than "always up". Without them (Oct 2026) the vote's hit rate was the same
# (54.0% vs 53.8% on 2019-24) and its worst drops smaller (34% vs 40%; from 2025 4% vs 6.5%).
VOTERS = {"ml": {"macro", "stress"}}
CALL_VOTES = {"buy": 1, "sell": -1, "hold": 0, "none": 0}
# One group alone is not "all agree".
MIN_GROUPS = 2


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


def group_calls(scores_by_source, group_lead):
    """{"rules": "buy", "ml": "hold", "opus": "none"} from {source: {agent: score}}."""
    return {source: group_call(voters(source, scores_by_source.get(source, {})), group_lead) for source in GROUPS}


def overall_net(groups):
    return sum(CALL_VOTES[signal] for signal in groups.values())


def overall_call(groups):
    """Round 2: Buy or Sell only when every group that voted says it; "none" when none voted."""
    voted = [signal for signal in groups.values() if signal != "none"]
    if not voted:
        return "none"
    if len(voted) >= MIN_GROUPS and len(set(voted)) == 1 and voted[0] in ("buy", "sell"):
        return voted[0]
    return "hold"


def decide(scores_by_source, rule):
    """(group calls, overall call) for one day under {"group_lead": g}."""
    groups = group_calls(scores_by_source, rule["group_lead"])
    return groups, overall_call(groups)
