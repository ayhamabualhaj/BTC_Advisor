def swing_points(values, window, is_high):
    """Values that are the highest (or lowest) within `window` days on each side."""
    points = []
    for i in range(window, len(values) - window):
        neighbours = values[i - window:i] + values[i + 1:i + window + 1]
        if (is_high and values[i] > max(neighbours)) or (not is_high and values[i] < min(neighbours)):
            points.append(values[i])
    return points


def support_resistance(highs, lows, close, lookback=90, window=5, tolerance_pct=3.0):
    """Nearest swing-low support below and swing-high resistance above the close.

    "Near" means within `tolerance_pct` percent of the close.
    """
    supports = [low for low in swing_points(lows[-lookback:], window, False) if low <= close]
    resistances = [high for high in swing_points(highs[-lookback:], window, True) if high >= close]
    support = max(supports, default=None)
    resistance = min(resistances, default=None)
    return {
        "support": support,
        "resistance": resistance,
        "near_support": support is not None and (close - support) / close * 100 <= tolerance_pct,
        "near_resistance": resistance is not None and (resistance - close) / close * 100 <= tolerance_pct,
    }
