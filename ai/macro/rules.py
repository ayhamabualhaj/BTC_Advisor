"""Macro rules, chosen by search on Jan 2025 - Sep 23 2026 (October held out).

Each rule was kept only if the set was right at least 60% of the time over 7 days on the
whole tuning period and in 2025 and 2026 separately. Stock sell-offs were followed by
Bitcoin rebounds; low inflation helped; a CPI print no cooler than its recent trend hurt.
The dollar, Fed and ETF-flow rules did not hold up and were dropped (they stay in the
Opus input).
"""

from ai.scoring import RuleScore, has

CALL_POINTS = 10
NASDAQ_DROP_5D_PCT = -4
NASDAQ_DROP_20D_PCT = -3
LOW_INFLATION_PCT = 2.7      # CPI year on year
CPI_NOT_COOLER_PCT = -0.04   # latest monthly change minus the previous 3 months' average


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "nasdaq_change_5d_pct"):
        result.skip("Nasdaq 5-day change")
    elif snapshot["nasdaq_change_5d_pct"] < NASDAQ_DROP_5D_PCT:
        result.add(f"Nasdaq down {-snapshot['nasdaq_change_5d_pct']:.1f}% in a week: rebound likely", CALL_POINTS)

    if not has(snapshot, "nasdaq_change_20d_pct"):
        result.skip("Nasdaq 20-day change")
    elif snapshot["nasdaq_change_20d_pct"] < NASDAQ_DROP_20D_PCT:
        result.add(f"Nasdaq down {-snapshot['nasdaq_change_20d_pct']:.1f}% in a month: rebound likely", CALL_POINTS)

    if not has(snapshot, "cpi_yoy_pct"):
        result.skip("Inflation")
    elif snapshot["cpi_yoy_pct"] < LOW_INFLATION_PCT:
        result.add(f"Inflation low at {snapshot['cpi_yoy_pct']:.1f}%", CALL_POINTS)

    if not has(snapshot, "cpi_surprise_pct"):
        result.skip("CPI")
    elif snapshot["cpi_surprise_pct"] > CPI_NOT_COOLER_PCT:
        result.add("Latest CPI no cooler than its recent trend", -CALL_POINTS)
    return result
