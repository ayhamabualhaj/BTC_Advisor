"""Derivatives rules, chosen by search on Jan 2025 - Sep 23 2026 (October held out).

Each rule was kept only if the set was right at least 60% of the time over 7 days on the
whole tuning period and close to that in 2025 and 2026 separately. The funding
thresholds are sensitive: small changes moved the hit rate between 58% and 60%.
"""

from ai.scoring import RuleScore, has

CALL_POINTS = 10
# Funding per 8 hours, as a fraction (0.0001 = 0.01%, the usual neutral level).
HIGH_FUNDING_30D = 0.000033  # longs paying more than usual for a month: crowded
LOW_FUNDING_7D = 0.000007    # little or no premium for a week: nobody is chasing
PRICE_JUMP_3D_PCT = 6
OI_COLLAPSE_3D_PCT = -9

# One day of long liquidations on OKX this large (in USD) counts as a flush. There is no
# liquidation history yet, so this rule could not be tuned; it stays small.
LARGE_LONG_LIQUIDATIONS_USD = 20_000_000
FLUSH_POINTS = 5


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "funding_rate_30d_avg"):
        result.skip("30-day funding")
    elif snapshot["funding_rate_30d_avg"] > HIGH_FUNDING_30D:
        result.add("Funding high over 30 days: crowded longs", -CALL_POINTS)

    if not has(snapshot, "funding_rate_7d_avg"):
        result.skip("7-day funding")
    elif snapshot["funding_rate_7d_avg"] < LOW_FUNDING_7D:
        result.add("Funding near zero or negative over 7 days", CALL_POINTS)

    if not has(snapshot, "price_change_3d_pct"):
        result.skip("3-day price change")
    elif snapshot["price_change_3d_pct"] > PRICE_JUMP_3D_PCT:
        result.add(f"Price up {snapshot['price_change_3d_pct']:.1f}% in 3 days", CALL_POINTS)

    if not has(snapshot, "open_interest_change_3d_pct"):
        result.skip("Open interest")
    elif snapshot["open_interest_change_3d_pct"] < OI_COLLAPSE_3D_PCT:
        result.add("Open interest collapsed over 3 days", -CALL_POINTS)

    if not has(snapshot, "long_liquidations_usd_1d"):
        result.skip("Liquidations")
    elif snapshot["long_liquidations_usd_1d"] >= LARGE_LONG_LIQUIDATIONS_USD:
        result.add("Large long liquidations: flush done", FLUSH_POINTS)
    return result
