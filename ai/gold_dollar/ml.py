"""Gold dollar ML agent: a logistic regression on the dollar's moves and gold against it,
retrained monthly (C = 0.1, the setting of Bitcoin's dollar agent)."""

from ai import ml, similarity

from ai.gold import training_cutoff  # noqa: F401

REGULARIZATION = 0.1


def features(snapshot, setup):
    return similarity.encode(setup)


def score(brief):
    cutoff = training_cutoff(brief.date)
    return ml.score(brief.ml_features, brief.training, regularization=REGULARIZATION, cache_key=("gold_dollar", cutoff))
