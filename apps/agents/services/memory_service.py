"""RAG memory: store each day's setup with how it turned out, retrieve the closest past ones."""

import datetime
import json

from ai import similarity
from ai.domains import DOMAINS
from apps.agents.models import MemoryCase
from apps.agents.services import rule_scoring_service
from apps.backtest.calibration import HORIZON_DAYS
from apps.backtest.repositories import price_repository

SIMILAR_CASES = 5
# The model sees a summary of this many closest past days: 5 single cases were mostly noise.
SIMILAR_DAYS = 50
# Fewer comparable past days than this and the summary is left out.
MIN_SIMILAR_DAYS = 20
# A day with fewer numbers than this (e.g. derivatives before Bybit's history starts in
# 2020) teaches the ML agent nothing but its label, so it is left out of training.
MIN_TRAINING_FEATURES = 3


def outcome_text(return_pct):
    word = "rose" if return_pct > 0 else "fell"
    return f"Price {word} {abs(return_pct):.2f}% over the next {HORIZON_DAYS} days"


def build_cases(agent, model_input, start, end):
    """Save a MemoryCase for every day in [start, end] whose 7-day outcome is known."""
    closes = price_repository.closes(start, end + datetime.timedelta(days=HORIZON_DAYS))
    saved = 0
    day = start
    while day <= end:
        later = day + datetime.timedelta(days=HORIZON_DAYS)
        if day in closes and later in closes:
            snapshot, _ = rule_scoring_service.score_agent(agent, day)
            setup = model_input(snapshot)
            ml_features = DOMAINS[agent].ml.features(snapshot, setup)
            return_pct = (closes[later] / closes[day] - 1) * 100
            MemoryCase.objects.update_or_create(date=day, agent=agent, defaults={
                "setup_summary": json.dumps(setup, sort_keys=True),
                "embedding": similarity.encode(setup),
                "ml_features": ml_features,
                "outcome": outcome_text(return_pct),
                "return_7d_pct": round(return_pct, 2),
            })
            saved += 1
        day += datetime.timedelta(days=1)
    return saved


def similar_cases(agent, date, model_input, limit=SIMILAR_CASES):
    """The past setups most like today's, using only cases whose outcome was known by `date`.

    A case from day D is only finished at the close of D + 7, so a backtest decision on
    `date` may only learn from cases dated `date - 7` or earlier.
    """
    cutoff = date - datetime.timedelta(days=HORIZON_DAYS)
    cases = list(MemoryCase.objects.filter(agent=agent, date__lte=cutoff, return_7d_pct__isnull=False))
    query = similarity.encode(model_input)
    if not cases or not query:
        return []
    feature_scales = similarity.scales([case.embedding for case in cases])
    scored = []
    for case in cases:
        gap = similarity.distance(query, case.embedding, feature_scales)
        if gap is not None:
            scored.append((gap, case))
    scored.sort(key=lambda pair: (pair[0], pair[1].date))
    return [case for _, case in scored[:limit]]


def known_cases(agent):
    """Every case of an agent with a known outcome, oldest first: [(date, ml_features, return_7d_pct)]."""
    rows = MemoryCase.objects.filter(agent=agent, return_7d_pct__isnull=False).order_by("date")
    return list(rows.values_list("date", "ml_features", "return_7d_pct"))


def training_cases(agent, date, cases=None):
    """What the ML agent may learn from on `date`: [(features, went_up)].

    Same cutoff as similar_cases: a case's outcome is known 7 days after its date. A domain
    whose model is retrained once a month moves the cutoff back to before the month began.
    """
    cutoff = DOMAINS[agent].ml.training_cutoff(date)
    cases = known_cases(agent) if cases is None else cases
    return [(features, return_pct > 0) for day, features, return_pct in cases
            if day <= cutoff and len(features) >= MIN_TRAINING_FEATURES]


def similar_summary(agent, date, model_input):
    """What the model sees about the past days most like today, computed here (never by
    the model): how often the price rose in the next 7 days, against all known days."""
    cases = similar_cases(agent, date, model_input, limit=SIMILAR_DAYS)
    if len(cases) < MIN_SIMILAR_DAYS:
        return None
    cutoff = date - datetime.timedelta(days=HORIZON_DAYS)
    every = list(MemoryCase.objects.filter(agent=agent, date__lte=cutoff, return_7d_pct__isnull=False)
                 .values_list("return_7d_pct", flat=True))
    moves = sorted(case.return_7d_pct for case in cases)
    return {
        "days_compared": len(cases),
        "share_up_after_7d_pct": round(sum(move > 0 for move in moves) / len(moves) * 100, 1),
        "median_move_7d_pct": round(moves[len(moves) // 2], 2),
        "all_past_days_share_up_pct": round(sum(move > 0 for move in every) / len(every) * 100, 1),
    }
