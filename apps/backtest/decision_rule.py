"""The combining rule: a vote. Each agent votes Buy (score >= 55), Sell (<= 45) or Hold.

Buy when Buy votes outnumber Sell votes by at least `min_net_votes`, Sell when the reverse;
otherwise Hold. Which agents vote (rules, rules + ML, ...) and the margin are chosen on
2019-2024 by choose_combining_rule. The system only advises buying: a Sell means stay out.
"""

from ai.scoring import BEARISH_AT, BULLISH_AT


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


def voters(scores_by_source, sources):
    """{"technical:rules": 60, "technical:ml": 48, ...} from {source: {agent: score}}."""
    return {f"{agent}:{source}": score for source in sources
            for agent, score in scores_by_source.get(source, {}).items()}
