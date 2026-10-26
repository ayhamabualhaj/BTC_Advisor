"""The machine-learning agents' models, trained on a domain's past numbers.

Walk-forward: a model only learns from past days whose 7-day outcome was already known,
so it never sees the future. score = chance (0-100) that the price is higher in 7 days.

Technical and derivatives use a strongly regularized logistic regression (it stays near
50 because nothing beat a coin flip there). Macro uses a small random forest, the only
model that held up on data it was never chosen on (see CLAUDE.md, "ML agents").
"""

import datetime
import math
from dataclasses import dataclass, field


# Fewer past days than this is too little to learn from; the agent abstains (no score).
MIN_CASES = 120
# Inverse regularization strength. Small = strong pull toward "no edge" (50), because
# neighbouring days share most of their 7-day window and look like more evidence than they are.
# Chosen walk-forward on 2019 - Sep 23 2026 (history from Aug 2017) from C 0.003-0.3 and
# 1-year, 2-year and full training windows: no setting beat a coin flip in every period, so
# the one with the best Brier score, which stays closest to 50, was kept (full history).
REGULARIZATION = 0.003
TOP_REASONS = 3
# A case from day D is finished at the close of D + 7.
HORIZON_DAYS = 7
# The forest: shallow trees with big leaves, so it can only learn broad patterns.
FOREST_TREES = 300
FOREST_DEPTH = 6
FOREST_MIN_LEAF = 50

# Fitted monthly models, so a backtest over years fits one forest per month, not per day.
_fitted = {}


@dataclass
class MLScore:
    score: int | None
    reasons: list = field(default_factory=list)
    cases: int = 0


def daily_cutoff(date):
    """The last case a model retrained every day may learn from."""
    return date - datetime.timedelta(days=HORIZON_DAYS)


def monthly_cutoff(date):
    """The last case a model retrained on the 1st of each month may learn from: its
    outcome was known before the month began."""
    return date.replace(day=1) - datetime.timedelta(days=HORIZON_DAYS + 1)


# scikit-learn is imported inside the builders: it takes a second to load, and pages that
# read stored scores never train a model.
def logistic(regularization=REGULARIZATION):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    # A feature missing on a past day is filled with that feature's median; one never seen
    # in training is kept as a constant column so the inputs keep their order.
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
                         LogisticRegression(C=regularization))


def forest():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline

    # add_indicator: a flag column per feature that was missing, so a gap is not read as the median.
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                         RandomForestClassifier(FOREST_TREES, max_depth=FOREST_DEPTH, min_samples_leaf=FOREST_MIN_LEAF,
                                                n_jobs=-1, random_state=0))


def fit(build, rows, labels, cache_key):
    if cache_key is None:
        return build().fit(rows, labels)
    key = (cache_key, len(rows))
    if key not in _fitted:
        _fitted[key] = build().fit(rows, labels)
    return _fitted[key]


def score(features, training, regularization=REGULARIZATION, build=None, cache_key=None):
    """features: today's {name: float}; training: [(features, went_up)] known by today.

    build: the model to fit (default: logistic regression). cache_key: reuse a model fitted
    on the same training (it must name everything the training depends on, e.g. the cutoff).
    """
    if len(training) < MIN_CASES:
        return MLScore(None, [f"Only {len(training)} past days to learn from (needs {MIN_CASES})"], len(training))
    labels = [went_up for _, went_up in training]
    if not features or len(set(labels)) < 2:
        return MLScore(None, ["Nothing to learn from"], len(training))
    # Only today's features: one that is missing today cannot say anything about today.
    names = sorted(features)
    rows = [[case.get(name, math.nan) for name in names] for case, _ in training]
    build = build or (lambda: logistic(regularization))
    model = fit(build, rows, labels, cache_key and (cache_key, tuple(names)))
    today = [[features[name] for name in names]]
    up = list(model.classes_).index(True)
    probability = model.predict_proba(today)[0][up]
    return MLScore(round(probability * 100), reasons(model, names, today, len(training)), len(training))


def reasons(model, names, today, cases):
    """The features that moved today's probability most, in the model's own units."""
    if not hasattr(model[-1], "coef_"):
        return forest_reasons(model, names, today, cases)
    standardized = model[:-1].transform(today)[0]
    coefficients = model[-1].coef_[0]
    pushes = sorted(zip(names, today[0], coefficients * standardized), key=lambda item: -abs(item[2]))
    lines = [f"Learned from {cases} past days"]
    for name, value, push in pushes[:TOP_REASONS]:
        if abs(push) >= 0.01:
            lines.append(f"{name} = {value:g} points {'up' if push > 0 else 'down'} ({push:+.2f})")
    return lines


def forest_reasons(model, names, today, cases):
    """A forest has no per-day push, so name the features it relies on most overall."""
    # The imputer puts the original features first, then the missing-value flags.
    importances = model[-1].feature_importances_[:len(names)]
    ranked = sorted(zip(names, today[0], importances), key=lambda item: -item[2])
    lines = [f"Random forest, learned from {cases} past days"]
    for name, value, importance in ranked[:TOP_REASONS]:
        lines.append(f"{name} = {value:g} (weight {importance:.0%})")
    return lines
