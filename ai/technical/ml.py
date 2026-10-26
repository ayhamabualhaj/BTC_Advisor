"""Technical ML agent: learns from past technical setups and how the price moved after them."""

from ai import ml, similarity


def features(snapshot, setup):
    return similarity.encode(setup)


def training_cutoff(date):
    return ml.daily_cutoff(date)


def score(brief):
    return ml.score(brief.ml_features, brief.training)
