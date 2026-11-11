"""Dollar ML agent: a logistic regression on the dollar index's moves, retrained monthly.

Added on Nov 11 2026 as a sixth voter of the strong signal only. Alone it is weak (about 60%
of its trades right on 2019-24, 55% from 2025); it earns its place by what it adds to the
other five: with it the strong signal was right in 38 of 53 trades on 2019-24 and 10 of 12
from 2025 (scratch test; the project's own numbers are in CLAUDE.md). C = 0.1 as tested.
"""

from ai import ml, similarity

REGULARIZATION = 0.1


def features(snapshot, setup):
    return similarity.encode(setup)


def training_cutoff(date):
    return ml.monthly_cutoff(date)


def score(brief):
    cutoff = training_cutoff(brief.date)
    return ml.score(brief.ml_features, brief.training, regularization=REGULARIZATION, cache_key=("dollar", cutoff))
