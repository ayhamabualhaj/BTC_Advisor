"""Derivatives ML agent: learns from past derivatives setups and how the price moved after them."""

from ai import ml, similarity


# Added to the Opus input with prompt v3; the ML model keeps the numbers it was tested on.
OPUS_ONLY = {"funding_rate_30d_avg_pct"}


def features(snapshot, setup):
    return similarity.encode({key: value for key, value in setup.items() if key not in OPUS_ONLY})


def training_cutoff(date):
    return ml.daily_cutoff(date)


def score(brief):
    return ml.score(brief.ml_features, brief.training)
