from apps.agents.scoring import RuleScore, has

# Moves smaller than these count as flat, so noise does not swing the score.
DXY_TREND_PCT = 0.5
CPI_SURPRISE_PCT = 0.05

DXY_POINTS = 10
NASDAQ_POINTS = 10
FED_CUT_POINTS = 10
FED_HIKE_POINTS = -15
CPI_POINTS = 5
ETF_POINTS = 10


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "dxy_change_2w_pct"):
        result.skip("Dollar index trend")
    elif snapshot["dxy_change_2w_pct"] < -DXY_TREND_PCT:
        result.add("Dollar index falling over 2 weeks", DXY_POINTS)
    elif snapshot["dxy_change_2w_pct"] > DXY_TREND_PCT:
        result.add("Dollar index rising over 2 weeks", -DXY_POINTS)

    if not has(snapshot, "nasdaq", "nasdaq_sma_50"):
        result.skip("Nasdaq trend")
    elif snapshot["nasdaq"] > snapshot["nasdaq_sma_50"]:
        result.add("Nasdaq above its 50-day average", NASDAQ_POINTS)
    else:
        result.add("Nasdaq below its 50-day average", -NASDAQ_POINTS)

    score_fed(snapshot, result)

    if not has(snapshot, "cpi_surprise_pct"):
        result.skip("CPI")
    elif snapshot["cpi_surprise_pct"] < -CPI_SURPRISE_PCT:
        result.add("CPI cooler than its recent trend", CPI_POINTS)
    elif snapshot["cpi_surprise_pct"] > CPI_SURPRISE_PCT:
        result.add("CPI hotter than its recent trend", -CPI_POINTS)

    if not has(snapshot, "etf_net_flow_5d_musd"):
        result.skip("ETF flows")
    elif snapshot["etf_net_flow_5d_musd"] > 0:
        result.add("Spot ETF net inflows over 5 days", ETF_POINTS)
    elif snapshot["etf_net_flow_5d_musd"] < 0:
        result.add("Spot ETF net outflows over 5 days", -ETF_POINTS)
    return result


def score_fed(snapshot, result):
    change = snapshot.get("fed_rate_change_60d")
    if change is None and snapshot.get("cuts_expected") is None:
        result.skip("Fed policy")
    elif change == 1:
        result.add("Fed hiked rates recently", FED_HIKE_POINTS)
    elif change == -1 or snapshot.get("cuts_expected"):
        result.add("Fed rate cut just happened or expected", FED_CUT_POINTS)
