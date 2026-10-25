"""The combining rule: buy only when enough agents are confident at the same time."""


def agents_above(scores, threshold):
    """How many agents score at or above the threshold. A missing score never counts."""
    return sum(1 for score in scores.values() if score is not None and score >= threshold)


def is_buy(scores, threshold, agents_required):
    return agents_above(scores, threshold) >= agents_required
