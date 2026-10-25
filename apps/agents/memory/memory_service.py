"""RAG memory: store each day's setup with how it turned out, retrieve the closest past ones."""

import datetime
import json

from apps.agents.memory import features
from apps.agents.models import MemoryCase
from apps.agents.services import rule_scoring_service
from apps.backtest.calibration import HORIZON_DAYS
from apps.backtest.repositories import price_repository

SIMILAR_CASES = 5


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
            return_pct = (closes[later] / closes[day] - 1) * 100
            MemoryCase.objects.update_or_create(date=day, agent=agent, defaults={
                "setup_summary": json.dumps(setup, sort_keys=True),
                "embedding": features.encode(setup),
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
    query = features.encode(model_input)
    if not cases or not query:
        return []
    feature_scales = features.scales([case.embedding for case in cases])
    scored = []
    for case in cases:
        gap = features.distance(query, case.embedding, feature_scales)
        if gap is not None:
            scored.append((gap, case))
    scored.sort(key=lambda pair: (pair[0], pair[1].date))
    return [case for _, case in scored[:limit]]


def as_model_input(cases):
    """What Opus sees about each similar case: the setup and what happened, no date."""
    return [
        {"setup": json.loads(case.setup_summary), "return_after_7d_pct": case.return_7d_pct}
        for case in cases
    ]
