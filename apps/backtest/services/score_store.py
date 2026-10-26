"""Rule and ML scores for many days, computed once and kept in DailyScore.

Scoring years of history takes minutes (the ML agent retrains for every day), so the
results are stored. The fingerprint is a hash of the code they depend on; changing a rule,
the ML model, an agent's inputs or an indicator gives a new fingerprint and the days are
scored again. The most recent days are never stored: their data can still be revised.
"""

import datetime
import hashlib
from pathlib import Path

from django.conf import settings

from apps.backtest.models import DailyScore
from apps.backtest.services import score_history

# Data for the last days is re-collected every morning, so their scores can still change.
FRESH_DAYS = 14
SOURCE_FILES = ["ai/*.py", "ai/*/rules.py", "ai/*/inputs.py", "ai/*/ml.py",
                "apps/data/indicators/*.py", "apps/data/services/indicator_service.py"]


def fingerprint():
    digest = hashlib.sha256()
    for pattern in SOURCE_FILES:
        for path in sorted(Path(settings.BASE_DIR).glob(pattern)):
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def scores(days, on_progress=None):
    """({day: {agent: rule_score}}, {day: {agent: ml_score}}) for the given days."""
    current = fingerprint()
    rules, ml = {}, {}
    for row in DailyScore.objects.filter(date__in=days, fingerprint=current):
        rules.setdefault(row.date, {})[row.agent] = row.rule_score
        ml.setdefault(row.date, {})[row.agent] = row.ml_score
    missing = [day for day in days if day not in rules]
    if missing:
        new_rules, new_ml = score_history.rule_and_ml_scores(missing, on_progress)
        rules.update(new_rules)
        ml.update(new_ml)
        store(new_rules, new_ml, current)
    return rules, ml


def store(rules, ml, current):
    last_stored = datetime.date.today() - datetime.timedelta(days=FRESH_DAYS)
    DailyScore.objects.exclude(fingerprint=current).delete()
    DailyScore.objects.bulk_create([
        DailyScore(date=day, agent=agent, rule_score=score, ml_score=ml[day].get(agent), fingerprint=current)
        for day, by_agent in rules.items() if day <= last_stored
        for agent, score in by_agent.items() if score is not None
    ], ignore_conflicts=True)
