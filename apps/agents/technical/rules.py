"""Technical rules, scored for mean reversion.

On the tuning period (Aug 2025 - Jun 2026, before the test period) trend-following
signals had no 7-day edge: being above the 50- or 200-day average or a MACD cross did
not predict a rise. Stretched short-term moves tended to partly revert. So stretch
counts against the move, the long trend only adds a little context, and the points are
small: price indicators alone rarely justify a confident score.
"""

from apps.agents.scoring import RuleScore, has

TREND_POINTS = 3
STRETCH_POINTS = 5
STRETCH_PCT = 5
RALLY_POINTS = 5
DIP_POINTS = 3
SWING_PCT = 5
RSI_POINTS = 5
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
LEVEL_POINTS = 3


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "close", "sma_200"):
        result.skip("200-day average")
    elif snapshot["close"] > snapshot["sma_200"]:
        result.add("Price above 200-day average", TREND_POINTS)
    else:
        result.add("Price below 200-day average", -TREND_POINTS)

    if not has(snapshot, "close", "sma_20"):
        result.skip("20-day average")
    else:
        stretch = (snapshot["close"] / snapshot["sma_20"] - 1) * 100
        if stretch > STRETCH_PCT:
            result.add(f"Price {stretch:.1f}% above 20-day average: stretched", -STRETCH_POINTS)
        elif stretch < -STRETCH_PCT:
            result.add(f"Price {-stretch:.1f}% below 20-day average: stretched", STRETCH_POINTS)

    if not has(snapshot, "change_7d_pct"):
        result.skip("7-day change")
    elif snapshot["change_7d_pct"] > SWING_PCT:
        result.add(f"Up {snapshot['change_7d_pct']:.1f}% in 7 days: likely to cool off", -RALLY_POINTS)
    elif snapshot["change_7d_pct"] < -SWING_PCT:
        result.add(f"Down {-snapshot['change_7d_pct']:.1f}% in 7 days: room to bounce", DIP_POINTS)

    if not has(snapshot, "rsi_14"):
        result.skip("RSI")
    elif snapshot["rsi_14"] < RSI_OVERSOLD:
        result.add(f"RSI {snapshot['rsi_14']:.0f}: oversold", RSI_POINTS)
    elif snapshot["rsi_14"] > RSI_OVERBOUGHT:
        result.add(f"RSI {snapshot['rsi_14']:.0f}: overbought", -RSI_POINTS)

    if snapshot.get("near_support"):
        result.add("Price near support", LEVEL_POINTS)
    if snapshot.get("near_resistance"):
        result.add("Price near resistance", -LEVEL_POINTS)
    return result
