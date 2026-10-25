"""Daily BTC perpetual liquidations from OKX (public, no key).

OKX only serves the last few days, so there is no history: the daily run collects it
going forward.
"""

import datetime
from collections import defaultdict

from .base import Point, get_json, utc_date

SOURCE = "okx"
URL = "https://www.okx.com/api/v5/public/liquidation-orders"
# One BTC-USDT-SWAP contract is 0.01 BTC.
CONTRACT_BTC = 0.01
MAX_PAGES = 500


def collect(start, end):
    details = []
    after = ""
    for _ in range(MAX_PAGES):
        params = {"instType": "SWAP", "uly": "BTC-USDT", "state": "filled", "limit": 100}
        if after:
            params["after"] = after
        data = get_json(URL, params)["data"]
        page = data[0]["details"] if data else []
        if not page:
            break
        details.extend(page)
        oldest = min(int(item["ts"]) for item in page)
        if utc_date(oldest) < start:
            break
        after = str(oldest)
    return parse_liquidations(details, start, end)


def parse_liquidations(details, start, end):
    """Sum liquidated USD per day and side. A long position is liquidated by a sell."""
    if not details:
        return []
    totals = defaultdict(float)
    for item in details:
        day = utc_date(int(item["ts"]))
        usd = float(item["sz"]) * CONTRACT_BTC * float(item["bkPx"])
        side = "long" if item["posSide"] == "long" else "short"
        totals[(day, side)] += usd
    # The oldest day is cut off by OKX's history limit and today is still running.
    first_full_day = min(utc_date(int(item["ts"])) for item in details) + datetime.timedelta(days=1)
    today = datetime.datetime.now(datetime.UTC).date()
    points = []
    for day in sorted({day for day, _ in totals}):
        if first_full_day <= day < today and start <= day <= end:
            points.append(Point(day, "long_liquidations_usd", totals[(day, "long")]))
            points.append(Point(day, "short_liquidations_usd", totals[(day, "short")]))
    return points
