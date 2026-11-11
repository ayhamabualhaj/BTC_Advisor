"""Gold stress ML agent: a logistic regression on VIX, MOVE and NFCI, retrained monthly (C = 0.1,
the setting of Bitcoin's stress agent; NFCI's first prints start in 2011)."""

from ai import ml, similarity

from ai.gold import training_cutoff  # noqa: F401

REGULARIZATION = 0.1


def features(snapshot, setup):
    return similarity.encode(setup)


def score(brief):
    cutoff = training_cutoff(brief.date)
    return ml.score(brief.ml_features, brief.training, regularization=REGULARIZATION, cache_key=("gold_stress", cutoff))
