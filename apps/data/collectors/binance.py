"""Daily BTC/USDT candles from Binance spot (public, no key)."""

import datetime

from .base import Point, get_json, to_ms, utc_date

SOURCE = "binance"
KLINES_URL = "https://api.binance.com/api/v3/klines"
PAGE_LIMIT = 1000
FIELDS = ("open", "high", "low", "close", "volume")


def collect(start, end):
    points = []
    cursor = to_ms(start)
    end_ms = to_ms(end + datetime.timedelta(days=1))
    while cursor < end_ms:
        candles = get_json(KLINES_URL, {
            "symbol": "BTCUSDT", "interval": "1d", "startTime": cursor,
            "endTime": end_ms - 1, "limit": PAGE_LIMIT,
        })
        if not candles:
            break
        points.extend(parse_candles(candles))
        cursor = candles[-1][0] + 1
    return points


def parse_candles(candles):
    """A daily candle opening at 00:00 on day D closes at the end of D, so it is dated D."""
    today = datetime.datetime.now(datetime.UTC).date()
    points = []
    for candle in candles:
        day = utc_date(candle[0])
        if day >= today:
            continue  # today's candle is still forming
        for field, raw in zip(FIELDS, candle[1:6]):
            points.append(Point(day, field, float(raw)))
    return points
