"""The combining rule: a vote in two rounds.

Round 1: each kind of agent votes among its three domains. The rule agents (technical,
derivatives, macro) give the Rules vote, the ML agents the ML vote, the Opus agents the
Opus vote. Each agent says Buy (score >= 55), Sell (<= 45) or Hold; the group says Buy when
its Buy votes lead its Sell votes by at least `group_lead`, Sell when the reverse.

Round 2: the three group votes vote the same way, by at least `overall_lead`. A group
with no scores (Opus on most past days) abstains. Both leads are chosen on 2019-2024 by
choose_combining_rule. The system only advises buying: a Sell means stay out.
"""

from ai.scoring import BEARISH_AT, BULLISH_AT

GROUPS = ["rules", "ml", "opus"]
CALL_VOTES = {"buy": 1, "sell": -1, "hold": 0, "none": 0}


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


def group_calls(scores_by_source, group_lead):
    """{"rules": "buy", "ml": "hold", "opus": "none"} from {source: {agent: score}}."""
    return {source: group_call(scores_by_source.get(source, {}), group_lead) for source in GROUPS}


def overall_net(groups):
    return sum(CALL_VOTES[signal] for signal in groups.values())


def overall_call(groups, overall_lead):
    """Round 2: the group votes vote; "none" when no group had any score."""
    if all(signal == "none" for signal in groups.values()):
        return "none"
    net = overall_net(groups)
    if net >= overall_lead:
        return "buy"
    if net <= -overall_lead:
        return "sell"
    return "hold"


def decide(scores_by_source, rule):
    """(group calls, overall call) for one day under {"group_lead": g, "overall_lead": o}."""
    groups = group_calls(scores_by_source, rule["group_lead"])
    return groups, overall_call(groups, rule["overall_lead"])
