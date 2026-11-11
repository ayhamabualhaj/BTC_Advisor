"""Gold macro ML agent: the same small random forest as Bitcoin's macro agent, retrained monthly.

Tested walk-forward on 2010-2023 (Nov 2026) against a logistic regression: neither beat the
fair rate of its own calls (forest 52.5% of 1624 on 2010-19, 49.8% of 532 on 2020-23); the
forest had the better Brier score and was kept. It is scored and shown; whether it votes is
decided with the vote (CLAUDE.md, "Gold").
"""

from ai import ml, similarity

from ai.gold import training_cutoff  # noqa: F401


def features(snapshot, setup):
    return similarity.encode(setup)


def score(brief):
    cutoff = training_cutoff(brief.date)
    return ml.score(brief.ml_features, brief.training, build=ml.forest, cache_key=("gold_macro", cutoff))
