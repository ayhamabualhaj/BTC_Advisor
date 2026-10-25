"""BTCUSDT perpetual data from Bybit (public, no key): funding, open interest, long/short."""

import datetime
from collections import defaultdict

from .base import Point, date_known_by, get_json, to_ms, utc_date

SOURCE = "bybit"
BASE_URL = "https://api.bybit.com/v5/market"
SYMBOL = "BTCUSDT"
# Bybit allows at most this many days per request for these endpoints.
WINDOW_DAYS = 60


def collect(start, end):
    return collect_funding(start, end) + collect_open_interest(start, end) + collect_long_short(start, end)


def windows(start, end):
    """Split [start, end] into chunks of WINDOW_DAYS, as (start_ms, end_ms) pairs."""
    day = start
    while day <= end:
        last = min(day + datetime.timedelta(days=WINDOW_DAYS - 1), end)
        yield to_ms(day), to_ms(last + datetime.timedelta(days=1)) - 1
        day = last + datetime.timedelta(days=1)


def collect_funding(start, end):
    rows = []
    # The last settlement of day `end` happens at 00:00 the next day, so fetch one day more.
    for start_ms, end_ms in windows(start, end + datetime.timedelta(days=1)):
        result = get_json(f"{BASE_URL}/funding/history", {
            "category": "linear", "symbol": SYMBOL,
            "startTime": start_ms, "endTime": end_ms, "limit": 200,
        })["result"]
        rows.extend(result["list"])
    return [point for point in parse_funding(rows) if start <= point.date <= end]


def parse_funding(rows):
    """Average the three 8-hour funding rates of each day into one daily rate."""
    by_day = defaultdict(list)
    for row in rows:
        by_day[date_known_by(int(row["fundingRateTimestamp"]))].append(float(row["fundingRate"]))
    return [
        Point(day, "funding_rate", sum(rates) / len(rates))
        for day, rates in sorted(by_day.items())
        if len(rates) == 3  # skip partial days at the edges of the range
    ]


def collect_paged(endpoint, params, start, end):
    rows = []
    for start_ms, end_ms in windows(start, end):
        cursor = ""
        while True:
            result = get_json(f"{BASE_URL}/{endpoint}", {
                **params, "category": "linear", "symbol": SYMBOL,
                "startTime": start_ms, "endTime": end_ms, "cursor": cursor,
            })["result"]
            rows.extend(result["list"])
            cursor = result.get("nextPageCursor") or ""
            if not cursor or not result["list"]:
                break
    return rows


def collect_open_interest(start, end):
    rows = collect_paged("open-interest", {"intervalTime": "1d", "limit": 200}, start, end)
    return parse_snapshots(rows, "openInterest", "open_interest")


def collect_long_short(start, end):
    rows = collect_paged("account-ratio", {"period": "1d", "limit": 500}, start, end)
    return parse_snapshots(rows, "buyRatio", "long_account_ratio")


def parse_snapshots(rows, key, field):
    """Daily snapshots are dated by their own timestamp day.

    Bybit does not say whether the stamp is the start or the end of the period, so we take
    the later reading: at worst the value is used one day late, never one day early.
    """
    points = {utc_date(int(row["timestamp"])): float(row[key]) for row in rows}
    return [Point(day, field, value) for day, value in sorted(points.items())]
