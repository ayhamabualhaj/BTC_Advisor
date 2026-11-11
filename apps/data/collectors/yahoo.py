"""Daily closes of the dollar index, US stock indexes and the MOVE index, and gold's daily candle,
from Yahoo Finance's chart API.

Calls the public chart endpoint directly instead of the yfinance package, which would add
pandas and several other libraries for a single request.
"""

import datetime
import zoneinfo

from .base import CollectorError, Point, get_json

SOURCE = "yahoo"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SYMBOLS = {
    "DX-Y.NYB": "dxy_close",
    "^IXIC": "nasdaq_close",
    "^GSPC": "sp500_close",
    "^MOVE": "move_close",  # bond market volatility (ICE BofA MOVE index)
}
# Gold: the front-month COMEX future (Yahoo has no clean spot series). Its whole candle is kept,
# as "gold_open" ... "gold_volume": the gold agents read it the way Bitcoin's read Binance's.
GOLD_SYMBOL = "GC=F"
GOLD_PREFIX = "gold_"
CANDLE_FIELDS = ("open", "high", "low", "close", "volume")


def collect(start, end):
    points = []
    for symbol, field in SYMBOLS.items():
        points.extend(collect_symbol(symbol, field, start, end))
    points.extend(parse_candles(fetch(GOLD_SYMBOL, start, end), GOLD_PREFIX))
    return points


def collect_symbol(symbol, field, start, end):
    return parse_chart(fetch(symbol, start, end), field)


def fetch(symbol, start, end):
    period1 = int(datetime.datetime.combine(start, datetime.time(), datetime.UTC).timestamp())
    period2 = int(datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time(), datetime.UTC).timestamp())
    payload = get_json(URL.format(symbol=symbol), {"period1": period1, "period2": period2, "interval": "1d"})
    result = (payload.get("chart") or {}).get("result")
    if not result:
        raise CollectorError(f"Yahoo returned no data for {symbol}")
    return result[0]


def session_days(result):
    """Each row's session day in the exchange's own time zone. The dollar index and gold are
    stamped at midnight New York time, and `gmtoffset` is only today's offset: used on a row
    from the other half of the year it would date the row a day early."""
    zone = zoneinfo.ZoneInfo(result["meta"]["exchangeTimezoneName"])
    return [datetime.datetime.fromtimestamp(stamp, zone).date() for stamp in result.get("timestamp", [])]


def parse_chart(result, field):
    closes = result["indicators"]["quote"][0]["close"]
    # A close of None is a holiday or half-filled row.
    return [Point(day, field, float(close)) for day, close in zip(session_days(result), closes) if close is not None]


def parse_candles(result, prefix):
    """The whole candle of each session; a session without a close is left out. Yahoo sometimes
    repeats a session: the later row replaces the earlier one."""
    quote = result["indicators"]["quote"][0]
    candles = {}
    for index, day in enumerate(session_days(result)):
        if quote["close"][index] is None:
            continue
        candles[day] = [Point(day, prefix + field, float(quote[field][index]))
                        for field in CANDLE_FIELDS if quote.get(field) and quote[field][index] is not None]
    return [point for day in sorted(candles) for point in candles[day]]
