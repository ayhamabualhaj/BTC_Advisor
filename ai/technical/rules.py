"""Technical rules, chosen by search on Jan 2025 - Sep 23 2026 (October held out).

Each rule was kept only if its calls were right at least 60% of the time over 7 days on
the whole tuning period and at least 55% in 2025 and in 2026 separately. A rule fires a
full call (10 points); opposite rules cancel to Hold.

The default is a mild sell: unless the long-term trend is already deeply down, a 7-day
window was more often lower than higher. Strong momentum, high volatility (often a
washed-out market) or a price far below its 200-day average override it with a buy.
"""

from ai.scoring import RuleScore, has

CALL_POINTS = 10
# 50-day average more than this far below the 200-day counts as a deep downtrend.
DEEP_DOWNTREND_PCT = -6
STRONG_RALLY_30D_PCT = 15
HIGH_VOLATILITY_PCT = 3.0  # standard deviation of daily moves over 14 days
FAR_BELOW_200D_PCT = -18


def pct(value, reference):
    return (value / reference - 1) * 100


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "sma_50", "sma_200"):
        result.skip("50- vs 200-day average")
    elif pct(snapshot["sma_50"], snapshot["sma_200"]) > DEEP_DOWNTREND_PCT:
        result.add("Long-term trend not deeply down: 7-day drift has been lower", -CALL_POINTS)

    if not has(snapshot, "change_30d_pct"):
        result.skip("30-day change")
    elif snapshot["change_30d_pct"] > STRONG_RALLY_30D_PCT:
        result.add(f"Up {snapshot['change_30d_pct']:.0f}% in 30 days: strong momentum", CALL_POINTS)

    if not has(snapshot, "volatility_14d_pct"):
        result.skip("Volatility")
    elif snapshot["volatility_14d_pct"] > HIGH_VOLATILITY_PCT:
        result.add(f"Daily moves of {snapshot['volatility_14d_pct']:.1f}%: high volatility", CALL_POINTS)

    if not has(snapshot, "close", "sma_200"):
        result.skip("200-day average")
    elif pct(snapshot["close"], snapshot["sma_200"]) < FAR_BELOW_200D_PCT:
        result.add("Price far below its 200-day average", CALL_POINTS)
    return result
