from apps.agents.scoring import RuleScore, has

MA_POINTS = 10
RSI_POINTS = 10
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
MACD_POINTS = 5
LEVEL_POINTS = 5


def score(snapshot):
    result = RuleScore()
    for period in (50, 200):
        key = f"sma_{period}"
        if not has(snapshot, "close", key):
            result.skip(f"{period}-day average")
        elif snapshot["close"] > snapshot[key]:
            result.add(f"Price above {period}-day average", MA_POINTS)
        else:
            result.add(f"Price below {period}-day average", -MA_POINTS)

    if not has(snapshot, "rsi_14"):
        result.skip("RSI")
    elif snapshot["rsi_14"] < RSI_OVERSOLD:
        result.add(f"RSI {snapshot['rsi_14']:.0f}: oversold", RSI_POINTS)
    elif snapshot["rsi_14"] > RSI_OVERBOUGHT:
        result.add(f"RSI {snapshot['rsi_14']:.0f}: overbought", -RSI_POINTS)

    if snapshot.get("macd_cross_3d") == "bullish":
        result.add("MACD bullish cross in the last 3 days", MACD_POINTS)
    elif snapshot.get("macd_cross_3d") == "bearish":
        result.add("MACD bearish cross in the last 3 days", -MACD_POINTS)

    if snapshot.get("near_support"):
        result.add("Price near support", LEVEL_POINTS)
    if snapshot.get("near_resistance"):
        result.add("Price near resistance", -LEVEL_POINTS)
    return result
