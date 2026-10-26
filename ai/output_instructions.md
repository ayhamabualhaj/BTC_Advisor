
## How to answer

The data comes as JSON. `null` means the number is not available today; do not guess it.
All numbers were calculated by code; do not recalculate them, reason about what they mean.
The asset and the date are deliberately not named. Judge only the numbers given.

The usual rate: over 2017-2024 the price was higher 7 days later on about 54% of days.
So with no information the right score is about 54, not 50.

`similar_past_days` summarizes the past days whose numbers were closest to today's (only
days whose outcome was already known): how many were compared, the share followed by a
higher price 7 days later, their median 7-day move, and the share for all past days. A
share well above or below the all-days share is some evidence; it is null when too few
days were comparable. It does not replace the patterns above.

Reply with:
- `opus_score`: an integer from 0 to 100, your confidence that the asset's price will be
  higher 7 days from now. 70 means you expect to be right about 70% of the time. Your
  scores are checked for calibration, so do not overstate confidence.
  A score of 55 or more is acted on as a Buy and 45 or less as a Sell. Give one only when
  at least one of the tested patterns is present and nothing important points the other
  way; otherwise answer between 46 and 54. Even a clear pattern rarely justifies more
  than 65 or less than 35.
- `direction`: "bullish" (score 55 or more), "bearish" (45 or less), otherwise "neutral".
- `reasons`: 3 to 5 short sentences, each linking specific numbers to your view. Name the
  tested pattern behind a call, or say that none is present.
- `suggested_stop_loss_pct`: how far below today's price, in percent, a stop loss for a
  long position should sit given what you see (for example 4.5).
