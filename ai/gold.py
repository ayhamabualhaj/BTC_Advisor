"""What gold's agents share.

Gold does not trade every day: the outcome of day D is the first close on or after D + 7,
which can come a few days later (a weekend, a holiday). A case is therefore only safe to
learn from that much later than Bitcoin's.
"""

import datetime

from ai import ml
from apps.data import assets

OUTCOME_WAIT = datetime.timedelta(days=assets.ASSETS["gold"].outcome_wait_days)


def training_cutoff(date):
    """Every gold model is retrained on the 1st of the month, on cases whose outcome was
    known before the month began."""
    return ml.monthly_cutoff(date) - OUTCOME_WAIT
