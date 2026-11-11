"""Gold technical ML agent: the same cautious logistic regression as Bitcoin's, retrained monthly.

Tested walk-forward on 2010-2023 (Nov 2026) with C 0.003 - 0.3 and a forest: none beat the
fair rate of its own calls (52-57% right, nearly all Buys, against a 53-55% base rate), so
the setting with the best Brier score, which stays closest to "no edge", was kept.
"""

from ai import ml, similarity

from ai.gold import training_cutoff  # noqa: F401


def features(snapshot, setup):
    return similarity.encode(setup)


def score(brief):
    cutoff = training_cutoff(brief.date)
    return ml.score(brief.ml_features, brief.training, cache_key=("gold_technical", cutoff))
