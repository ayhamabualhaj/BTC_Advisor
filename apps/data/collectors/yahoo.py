"""Daily closes of the dollar index, US stock indexes and the MOVE index from Yahoo Finance's chart API.

Calls the public chart endpoint directly instead of the yfinance package, which would add
pandas and several other libraries for a single request.
"""

import datetime

from .base import CollectorError, Point, get_json

SOURCE = "yahoo"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SYMBOLS = {
    "DX-Y.NYB": "dxy_close",
    "^IXIC": "nasdaq_close",
    "^GSPC": "sp500_close",
    "^MOVE": "move_close",  # bond market volatility (ICE BofA MOVE index)
}


def collect(start, end):
    points = []
    for symbol, field in SYMBOLS.items():
        points.extend(collect_symbol(symbol, field, start, end))
    return points


def collect_symbol(symbol, field, start, end):
    period1 = int(datetime.datetime.combine(start, datetime.time(), datetime.UTC).timestamp())
    period2 = int(datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time(), datetime.UTC).timestamp())
    payload = get_json(URL.format(symbol=symbol), {"period1": period1, "period2": period2, "interval": "1d"})
    result = (payload.get("chart") or {}).get("result")
    if not result:
        raise CollectorError(f"Yahoo returned no data for {symbol}")
    return parse_chart(result[0], field)


def parse_chart(result, field):
    """US markets close the same UTC day they open, so each close is dated by its session."""
    offset = datetime.timedelta(seconds=result["meta"].get("gmtoffset", 0))
    closes = result["indicators"]["quote"][0]["close"]
    points = []
    for stamp, close in zip(result.get("timestamp", []), closes):
        if close is None:
            continue  # holiday or half-filled row
        day = (datetime.datetime.fromtimestamp(stamp, datetime.UTC) + offset).date()
        points.append(Point(day, field, float(close)))
    return points
