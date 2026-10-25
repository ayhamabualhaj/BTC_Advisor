def sma(values, period):
    """Simple moving average of the last `period` values, or None if there are too few."""
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values, period):
    """Exponential moving average for every value; None until `period` values exist.

    Seeded with the simple average of the first `period` values, the usual convention.
    """
    result = [None] * len(values)
    if period <= 0 or len(values) < period:
        return result
    alpha = 2 / (period + 1)
    current = sum(values[:period]) / period
    result[period - 1] = current
    for index in range(period, len(values)):
        current = alpha * values[index] + (1 - alpha) * current
        result[index] = current
    return result


def pct_change(values, periods):
    """Percent change from `periods` values ago to the last value."""
    if periods <= 0 or len(values) <= periods or values[-1 - periods] == 0:
        return None
    return (values[-1] / values[-1 - periods] - 1) * 100


def rolling_sum(values, period):
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:])
