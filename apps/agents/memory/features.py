"""Turns an agent's model input into numbers and measures how alike two setups are.

The setups are already a handful of meaningful numbers, so they serve as their own
embedding: no text-embedding model or extra service is needed.
"""

import math

CATEGORIES = {
    "bullish": 1.0, "bearish": -1.0,  # MACD cross
    "cut": -1.0, "hike": 1.0, "none": 0.0,  # Fed move
}


def encode(model_input):
    """{feature: float} for every value that is present. Missing values are left out."""
    features = {}
    for key, value in model_input.items():
        if isinstance(value, bool):
            features[key] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)):
            features[key] = float(value)
        elif isinstance(value, str) and value in CATEGORIES:
            features[key] = CATEGORIES[value]
    return features


def scales(feature_sets):
    """Standard deviation of each feature, so a 1-point RSI move and a 1% price move compare fairly."""
    values = {}
    for features in feature_sets:
        for key, value in features.items():
            values.setdefault(key, []).append(value)
    result = {}
    for key, column in values.items():
        mean = sum(column) / len(column)
        spread = math.sqrt(sum((v - mean) ** 2 for v in column) / len(column))
        result[key] = spread or 1.0
    return result


# A feature today has but the past case lacks counts as this many standard deviations
# apart, so cases with gaps (e.g. before the 200-day average existed) do not look closer.
MISSING_GAP = 2.0


def distance(query, case, feature_scales, min_shared=0.5):
    """Root-mean-square standardized gap over today's features; None if too few are shared."""
    shared = [key for key in query if key in case]
    if not query or len(shared) < len(query) * min_shared:
        return None
    total = sum(((query[k] - case[k]) / feature_scales.get(k, 1.0)) ** 2 for k in shared)
    total += (len(query) - len(shared)) * MISSING_GAP ** 2
    return math.sqrt(total / len(query))
