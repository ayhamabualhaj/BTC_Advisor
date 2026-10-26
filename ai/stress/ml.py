"""Financial stress ML agent: a logistic regression on VIX, MOVE and NFCI, retrained monthly.

The one candidate of 36 that passed the test in Oct 2026: trained on 2017-2024, it was
right on 77.6% of 107 calls (7 days) from 2025, in 15 separate episodes, mostly Buys when
stocks were scared. Learned before each of 2021-2023 and judged on that year it beat a fair
baseline by only 1-5 points, so the real edge is probably modest. C = 0.1 as tested.
"""

from ai import ml, similarity

REGULARIZATION = 0.1


def features(snapshot, setup):
    return similarity.encode(setup)


def training_cutoff(date):
    return ml.monthly_cutoff(date)


def score(brief):
    cutoff = training_cutoff(brief.date)
    return ml.score(brief.ml_features, brief.training, regularization=REGULARIZATION, cache_key=("stress", cutoff))
