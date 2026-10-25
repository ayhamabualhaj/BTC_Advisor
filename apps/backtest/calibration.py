"""Calibration: when an agent says 80%, is it right about 80% of the time?

A score s is read as "s% chance the price is higher after the horizon". Above 50 that is an
up call with confidence s, below 50 a down call with confidence 100 - s; exactly 50 is no call.
"""

import datetime
from dataclasses import dataclass

HORIZON_DAYS = 7  # the horizon the Opus prompt asks about


@dataclass
class Bucket:
    label: str           # "60s" holds confidences 60-69
    calls: int
    hit_rate: float      # percent of calls that were right
    avg_confidence: float


def confidence(score):
    return max(score, 100 - score)


def bucket_label(conf):
    return f"{min(int(conf // 10) * 10, 90)}s"


def calibration_table(pairs):
    """pairs: (score, forward_return). Returns buckets from least to most confident."""
    groups = {}
    for score, forward_return in pairs:
        if score == 50 or forward_return == 0:
            continue
        conf = confidence(score)
        right = (score > 50) == (forward_return > 0)
        groups.setdefault(bucket_label(conf), []).append((conf, right))
    return [
        Bucket(label, len(calls), sum(r for _, r in calls) / len(calls) * 100,
               sum(c for c, _ in calls) / len(calls))
        for label, calls in sorted(groups.items())
    ]


def brier_score(pairs):
    """Mean squared gap between the stated chance and what happened (0 is perfect, 0.25 is
    what always saying 50 gets)."""
    terms = [(score / 100 - (1 if forward_return > 0 else 0)) ** 2 for score, forward_return in pairs]
    return sum(terms) / len(terms) if terms else None


def forward_returns(days, closes, horizon=HORIZON_DAYS):
    """{day: return from that day's close to the close `horizon` days later} where both exist."""
    result = {}
    for day in days:
        later = day + datetime.timedelta(days=horizon)
        if day in closes and later in closes:
            result[day] = closes[later] / closes[day] - 1
    return result
