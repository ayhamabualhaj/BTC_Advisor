"""Gold technical rule, from the pattern screen on 2005-2019 (Nov 2026).

Every number of the setup was tried in its top and bottom fifth. A pattern was kept only if
the share of up weeks after it moved the same way in each of 2005-09, 2010-14 and 2015-19
against that block's own base rate, and by 4 points or more overall. One technical pattern
passed: a low RSI was followed by more up weeks (+4.8 points; +3.4 / +8.8 / +2.6 per block;
+8.9 on 2020-23, -1.0 on 2024-26). Gold bought its dips. Nothing pointed down, so this rule
never says Sell. See CLAUDE.md, "Gold".
"""

from ai.scoring import RuleScore, has

CALL_POINTS = 10
# The bottom fifth of RSI (14) on 2005-2019.
LOW_RSI = 42


def score(snapshot):
    result = RuleScore()
    if not has(snapshot, "rsi_14"):
        result.skip("RSI")
    elif snapshot["rsi_14"] <= LOW_RSI:
        result.add(f"RSI {snapshot['rsi_14']:.0f}: gold's dips were bought more often than not", CALL_POINTS)
    return result
