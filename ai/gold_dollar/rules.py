"""Gold dollar rule, from the pattern screen on 2005-2019 (Nov 2026; see ai/gold_technical/rules.py).

One pattern passed: when gold's 20-day move trailed the dollar's by more than 3.8 points (the
bottom fifth), gold rose more often over the next week (+4.0 points; +1.5 / +8.3 / +0.6 per
block; +7.5 on 2020-23, -3.7 on 2024-26). Another dip that was bought. It never says Sell.
"""

from ai.scoring import RuleScore, has

CALL_POINTS = 10
# The bottom fifth of gold's 20-day move minus the dollar's, on 2005-2019.
FAR_BEHIND_DOLLAR_PCT = -3.8


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "gold_minus_dxy_20d_pct"):
        result.skip("Gold against the dollar")
    elif snapshot["gold_minus_dxy_20d_pct"] <= FAR_BEHIND_DOLLAR_PCT:
        result.add(f"Gold trails the dollar by {-snapshot['gold_minus_dxy_20d_pct']:.1f} points over 20 days: "
                   f"it has tended to catch up", CALL_POINTS)
    return result
