
## How to answer

The data comes as JSON. `null` means the number is not available today; do not guess it.
All numbers were calculated by code; do not recalculate them, reason about what they mean.
The asset and the date are deliberately not named. Judge only the numbers given.

`similar_past_setups` lists up to 5 earlier days whose numbers were closest to today's,
with how the price moved over the 7 days after each. Treat them as weak evidence: a
handful of cases can easily point the wrong way, and today's numbers come first.

Reply with:
- `opus_score`: an integer from 0 to 100, your confidence that the asset's price will be
  higher 7 days from now. 50 means no edge either way, 70 means you expect to be right
  about 70% of the time. Your scores are checked for calibration, so do not overstate
  confidence: most days deserve a score between 40 and 60.
- `direction`: "bullish" (score 55 or more), "bearish" (45 or less), otherwise "neutral".
- `reasons`: 3 to 5 short sentences, each linking specific numbers to your view.
- `suggested_stop_loss_pct`: how far below today's price, in percent, a stop loss for a
  long position should sit given what you see (for example 4.5).
