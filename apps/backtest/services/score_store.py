"""Rule and ML scores for many days, computed once and kept in DailyScore.

Scoring years of history takes minutes (the ML agent retrains for every day), so the
results are stored. The fingerprint is a hash of the code they depend on; changing a rule,
the ML model, an agent's inputs or an indicator gives a new fingerprint and the days are
scored again. The most recent days are never stored: their data can still be revised, so
they are kept in this process's memory for up to an hour instead (new data clears them).
"""

import datetime
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from apps.backtest.models import DailyScore
from apps.data.models import MarketData
from apps.backtest.services import score_history

# Data for the last days is re-collected every morning, so their scores can still change.
FRESH_DAYS = 14
FRESH_CACHE_SECONDS = 3600
# Only the code rule and ML scores depend on: editing the Opus client, prompts or the Flow
# must not throw away years of stored scores.
SOURCE_FILES = ["ai/scoring.py", "ai/ml.py", "ai/similarity.py", "ai/domains.py",
                "ai/*/rules.py", "ai/*/inputs.py", "ai/*/ml.py",
                "apps/agents/services/memory_service.py", "apps/agents/services/rule_scoring_service.py",
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
        rules.setdefault(row.date, {})[row.agent] = row.rule_score  # None for a domain without rules
        ml.setdefault(row.date, {})[row.agent] = row.ml_score
    missing = [day for day in days if day not in rules]
    version = data_version()
    keys = {day: f"scores:{current}:{version}:{day.isoformat()}" for day in missing}
    for day, (day_rules, day_ml) in ((day, cached) for day, key in keys.items()
                                      if (cached := cache.get(key)) is not None):
        rules[day], ml[day] = day_rules, day_ml
    missing = [day for day in missing if day not in rules]
    if missing:
        new_rules, new_ml = score_history.rule_and_ml_scores(missing, on_progress)
        rules.update(new_rules)
        ml.update(new_ml)
        store(new_rules, new_ml, current)
        cache.set_many({keys[day]: (new_rules[day], new_ml[day]) for day in missing}, FRESH_CACHE_SECONDS)
    return rules, ml


def data_version():
    # The newest MarketData row changes whenever data is collected, which clears the memory.
    return MarketData.objects.order_by("-id").values_list("id", flat=True).first()


def store(rules, ml, current):
    last_stored = datetime.date.today() - datetime.timedelta(days=FRESH_DAYS)
    DailyScore.objects.exclude(fingerprint=current).delete()
    DailyScore.objects.bulk_create([
        DailyScore(date=day, agent=agent, rule_score=rules[day].get(agent), ml_score=ml[day].get(agent), fingerprint=current)
        for day in rules if day <= last_stored
        # A domain without rules (stress) is stored for its ML score.
        for agent in rules[day].keys() | ml[day].keys()
        if rules[day].get(agent) is not None or ml[day].get(agent) is not None
    ], ignore_conflicts=True)
