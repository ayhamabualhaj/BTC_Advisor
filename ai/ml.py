"""The machine-learning agents' model: logistic regression on a domain's setup numbers.

It is retrained for every decision day on the past days whose 7-day outcome was already
known (walk-forward), so it never learns from the future. Logistic regression because a
few hundred overlapping days are too little for anything bigger, and it gives a
probability directly: score = chance (0-100) that the price is higher in 7 days.
"""

import math
from dataclasses import dataclass, field

from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Fewer past days than this is too little to learn from; the agent abstains (no score).
MIN_CASES = 120
# Inverse regularization strength. Small = strong pull toward "no edge" (50), because
# neighbouring days share most of their 7-day window and look like more evidence than they are.
# Chosen walk-forward on 2019 - Sep 23 2026 (history from Aug 2017) from C 0.003-0.3 and
# 1-year, 2-year and full training windows: no setting beat a coin flip in every period, so
# the one with the best Brier score, which stays closest to 50, was kept (full history).
REGULARIZATION = 0.003
TOP_REASONS = 3


@dataclass
class MLScore:
    score: int | None
    reasons: list = field(default_factory=list)
    cases: int = 0


def build_model(regularization):
    # A feature missing on a past day is filled with that feature's median; one never seen
    # in training is kept as a constant column so the inputs keep their order.
    return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
                         LogisticRegression(C=regularization))


def score(features, training, regularization=REGULARIZATION):
    """features: today's {name: float}; training: [(features, went_up)] known by today."""
    if len(training) < MIN_CASES:
        return MLScore(None, [f"Only {len(training)} past days to learn from (needs {MIN_CASES})"], len(training))
    labels = [went_up for _, went_up in training]
    if not features or len(set(labels)) < 2:
        return MLScore(None, ["Nothing to learn from"], len(training))
    # Only today's features: one that is missing today cannot say anything about today.
    names = sorted(features)
    rows = [[case.get(name, math.nan) for name in names] for case, _ in training]
    model = build_model(regularization).fit(rows, labels)
    today = [[features[name] for name in names]]
    up = list(model.classes_).index(True)
    probability = model.predict_proba(today)[0][up]
    return MLScore(round(probability * 100), reasons(model, names, today, len(training)), len(training))


def reasons(model, names, today, cases):
    """The features that moved today's probability most, in the model's own units."""
    standardized = model[:-1].transform(today)[0]
    coefficients = model[-1].coef_[0]
    pushes = sorted(zip(names, today[0], coefficients * standardized), key=lambda item: -abs(item[2]))
    lines = [f"Learned from {cases} past days"]
    for name, value, push in pushes[:TOP_REASONS]:
        if abs(push) >= 0.01:
            lines.append(f"{name} = {value:g} points {'up' if push > 0 else 'down'} ({push:+.2f})")
    return lines
