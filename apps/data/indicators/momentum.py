from .trend import ema_series


def rsi(closes, period=14):
    """Wilder's Relative Strength Index of the last close (0-100)."""
    if len(closes) <= period:
        return None
    changes = [later - earlier for earlier, later in zip(closes, closes[1:])]
    avg_gain = sum(max(c, 0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0) for c in changes[:period]) / period
    # Wilder's smoothing: each new change counts 1/period.
    for change in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(change, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0)) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def macd_series(closes, fast=12, slow=26, signal=9):
    """MACD line and signal line for every close (None during warm-up)."""
    fast_ema, slow_ema = ema_series(closes, fast), ema_series(closes, slow)
    macd = [f - s if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)]
    first = next((i for i, value in enumerate(macd) if value is not None), len(macd))
    signal_tail = ema_series(macd[first:], signal)
    return macd, [None] * first + signal_tail


def macd_cross(closes, lookback=3):
    """'bullish' or 'bearish' if MACD crossed its signal line in the last `lookback` days."""
    macd, signal = macd_series(closes)
    diffs = [m - s if m is not None and s is not None else None for m, s in zip(macd, signal)]
    recent = diffs[-(lookback + 1):]
    if len(recent) < lookback + 1 or None in recent:
        return None
    # Look at the most recent cross first.
    for before, after in reversed(list(zip(recent, recent[1:]))):
        if before <= 0 < after:
            return "bullish"
        if before >= 0 > after:
            return "bearish"
    return None
