"""Gold stress rule, from the pattern screen on 2005-2019 (Nov 2026; see ai/gold_technical/rules.py).

One pattern passed: with the VIX in its top fifth, gold rose more often over the next week
(+4.8 points; +0.2 / +2.6 / +23.7 per block, so most of it is 2015-19; -1.8 on 2020-23,
+4.5 on 2024-26). The weakest of gold's three rules. It never says Sell.
"""

from ai.scoring import RuleScore, has

CALL_POINTS = 10
# The top fifth of the VIX on 2005-2019.
HIGH_VIX = 22.7


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "vix"):
        result.skip("VIX")
    elif snapshot["vix"] >= HIGH_VIX:
        result.add(f"VIX {snapshot['vix']:.1f}: scared stock markets were followed by a stronger gold week", CALL_POINTS)
    return result
