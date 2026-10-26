"""Risk-on day rule: Bitcoin and the Nasdaq both up today -> Sell for tomorrow.

Found in Oct 2026 by looking at 60 markets on 2017-2026: after a day when Bitcoin and US
stocks rose together, Bitcoin rose the next day less often. Right the next day 52-57% in
2018-2024 (fair 45-54%) and 58.4% of 149 calls from 2025 (+52.7% holding Bitcoin but out
on its Sell days, vs -15.3%). Not a clean test: the Nasdaq was picked after seeing
2025-26, a version learned only from 2017-24 did not pick it, and the luck check gave p
0.045. It is a 1-day call; over 7 days it is a coin flip (51.4%). It never says Buy.
"""

from ai.scoring import RuleScore, has

CALL_POINTS = 10


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "btc_change_1d_pct", "nasdaq_change_1d_pct"):
        # Weekends and US holidays: the Nasdaq did not trade, so there is no call.
        result.skip("Bitcoin and Nasdaq moves today")
    elif snapshot["btc_change_1d_pct"] > 0 and snapshot["nasdaq_change_1d_pct"] > 0:
        result.add(f"Bitcoin up {snapshot['btc_change_1d_pct']:.1f}% and Nasdaq up {snapshot['nasdaq_change_1d_pct']:.1f}% "
                   f"today: the next day is often weaker", -CALL_POINTS)
    return result
