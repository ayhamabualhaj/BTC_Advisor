from apps.agents.scoring import RuleScore, has

# Funding per 8 hours. The neutral rate on most exchanges is 0.01%; three times that
# means longs are paying heavily to stay in, a sign of a crowded long side.
HIGH_FUNDING = 0.0003
HIGH_FUNDING_POINTS = -15
NEGATIVE_FUNDING_POINTS = 10

# Open interest change over 3 days that counts as "rising".
OI_RISING_PCT = 2.0
OI_WITH_PRICE_POINTS = 5
OI_AGAINST_PRICE_POINTS = -10

# One day of long liquidations on OKX this large (in USD) counts as a flush.
LARGE_LONG_LIQUIDATIONS_USD = 20_000_000
FLUSH_POINTS = 10

# How far the share of accounts long may drift from its 90-day average before the crowd
# counts as extreme.
CROWD_DEVIATION = 0.08
CROWD_POINTS = 10


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "funding_rate"):
        result.skip("Funding rate")
    elif snapshot["funding_rate"] > HIGH_FUNDING:
        result.add("Funding very high: crowded longs", HIGH_FUNDING_POINTS)
    elif snapshot["funding_rate"] < 0:
        result.add("Funding negative: crowded shorts", NEGATIVE_FUNDING_POINTS)

    if not has(snapshot, "open_interest_change_3d_pct", "price_change_3d_pct"):
        result.skip("Open interest trend")
    elif snapshot["open_interest_change_3d_pct"] > OI_RISING_PCT:
        if snapshot["price_change_3d_pct"] > 0:
            result.add("Open interest rising with price", OI_WITH_PRICE_POINTS)
        else:
            result.add("Open interest rising while price falls", OI_AGAINST_PRICE_POINTS)

    if not has(snapshot, "long_liquidations_usd_1d"):
        result.skip("Liquidations")
    elif snapshot["long_liquidations_usd_1d"] >= LARGE_LONG_LIQUIDATIONS_USD:
        result.add("Large long liquidations: flush done", FLUSH_POINTS)

    if not has(snapshot, "long_account_ratio", "long_account_ratio_90d_avg"):
        result.skip("Long/short ratio")
    else:
        deviation = snapshot["long_account_ratio"] - snapshot["long_account_ratio_90d_avg"]
        # Contrarian: lean against an extreme crowd.
        if deviation > CROWD_DEVIATION:
            result.add("Long/short ratio extreme long: fade the crowd", -CROWD_POINTS)
        elif deviation < -CROWD_DEVIATION:
            result.add("Long/short ratio extreme short: fade the crowd", CROWD_POINTS)
    return result
