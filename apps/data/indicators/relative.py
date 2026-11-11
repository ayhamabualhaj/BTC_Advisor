"""How Bitcoin moves against another market: pure math on lists, no Django."""

import math


def returns(values):
    """The change from each value to the next, as shares."""
    return [later / earlier - 1 for earlier, later in zip(values, values[1:])]


def correlation(first, second):
    """Pearson correlation of two equally long lists; None when one of them never moves."""
    count = len(first)
    if count < 2 or count != len(second):
        return None
    mean_first, mean_second = sum(first) / count, sum(second) / count
    spread_first = math.sqrt(sum((value - mean_first) ** 2 for value in first))
    spread_second = math.sqrt(sum((value - mean_second) ** 2 for value in second))
    if not spread_first or not spread_second:
        return None
    together = sum((a - mean_first) * (b - mean_second) for a, b in zip(first, second))
    return together / (spread_first * spread_second)
