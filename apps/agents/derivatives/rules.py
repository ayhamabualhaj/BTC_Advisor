"""Derivatives rules, kept to what held up.

On the tuning period (Aug 2025 - Jun 2026, before the test period) two older rules were
wrong: open interest rising while the price fell was not bearish, and fading an extreme
long/short crowd pointed the wrong way (an unusually long crowd was followed by more up
weeks). Both are gone. Negative funding was mildly bullish. Positioning alone rarely
justifies a confident score, so the points are small.
"""

from apps.agents.scoring import RuleScore, has

# Funding per 8 hours. The neutral rate on most exchanges is 0.01%; three times that
# means longs are paying heavily to stay in, a sign of a crowded long side.
HIGH_FUNDING = 0.0003
HIGH_FUNDING_POINTS = -5
NEGATIVE_FUNDING_POINTS = 5

# One day of long liquidations on OKX this large (in USD) counts as a flush.
LARGE_LONG_LIQUIDATIONS_USD = 20_000_000
FLUSH_POINTS = 5


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "funding_rate"):
        result.skip("Funding rate")
    elif snapshot["funding_rate"] > HIGH_FUNDING:
        result.add("Funding very high: crowded longs", HIGH_FUNDING_POINTS)
    elif snapshot["funding_rate"] < 0:
        result.add("Funding negative: shorts are paying", NEGATIVE_FUNDING_POINTS)

    if not has(snapshot, "long_liquidations_usd_1d"):
        result.skip("Liquidations")
    elif snapshot["long_liquidations_usd_1d"] >= LARGE_LONG_LIQUIDATIONS_USD:
        result.add("Large long liquidations: flush done", FLUSH_POINTS)
    return result
