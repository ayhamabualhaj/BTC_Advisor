"""US rates, inflation, VIX and financial conditions from the FRED API (free key in FRED_API_KEY)."""

import bisect
import datetime

from django.conf import settings

from .base import CollectorError, Point, get_json

SOURCE = "fred"
URL = "https://api.stlouisfed.org/fred"
# Daily series: FRED publishes them the next business day, so each value is dated one day
# later than its observation date to stay safe in backtests.
DAILY_SERIES = {
    "DFF": "fed_funds_effective",
    "DFEDTARU": "fed_target_upper",
    "DGS2": "treasury_2y",
    "VIXCLS": "vix",
}
# Weekly series, dated by when they were known: NFCI covers the week to Friday and is
# published the next Wednesday, so it is dated 6 days after its observation date.
WEEKLY_SERIES = {
    "NFCI": ("nfci", 6),
}
# Monthly series: an observation for June is only released in mid-July.
MONTHLY_SERIES = {
    "CPIAUCSL": "cpi",
    "CPILFESL": "core_cpi",
}


def collect(start, end):
    if not settings.FRED_API_KEY:
        raise CollectorError("FRED_API_KEY is not set in .env (free key from fred.stlouisfed.org)")
    points = []
    for series, field in DAILY_SERIES.items():
        points.extend(parse_daily(fetch_observations(series, start, end), field))
    for series, (field, lag_days) in WEEKLY_SERIES.items():
        points.extend(parse_daily(fetch_observations(series, start - datetime.timedelta(days=14), end), field, lag_days))
    # Fetch monthly data from a year earlier so year-over-year inflation can be computed.
    monthly_start = start.replace(year=start.year - 1)
    for series, field in MONTHLY_SERIES.items():
        observations = fetch_observations(series, monthly_start, end)
        release_dates = fetch_release_dates(series, monthly_start)
        points.extend(parse_monthly(observations, release_dates, field))
    return [p for p in points if p.date <= end]


def call(path, **params):
    return get_json(f"{URL}/{path}", {**params, "api_key": settings.FRED_API_KEY, "file_type": "json"})


def fetch_observations(series, start, end):
    return call("series/observations", series_id=series,
                observation_start=start.isoformat(), observation_end=end.isoformat())["observations"]


def fetch_release_dates(series, start):
    dates = call("series/vintagedates", series_id=series, realtime_start=start.isoformat())["vintage_dates"]
    return sorted(datetime.date.fromisoformat(d) for d in dates)


def parse_daily(observations, field, lag_days=1):
    points = []
    for row in observations:
        if row["value"] == ".":
            continue  # FRED's marker for a missing day
        day = datetime.date.fromisoformat(row["date"]) + datetime.timedelta(days=lag_days)
        points.append(Point(day, field, float(row["value"])))
    return points


def parse_monthly(observations, release_dates, field):
    """Date each monthly value by the first release after its month ended.

    Values are the latest revision, which can differ slightly from the first print; the
    release date is what matters to avoid look-ahead.
    """
    points = []
    for row in observations:
        if row["value"] == ".":
            continue
        month = datetime.date.fromisoformat(row["date"])
        month_end = (month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        index = bisect.bisect_left(release_dates, month_end)
        if index == len(release_dates):
            continue  # not released yet
        points.append(Point(release_dates[index], field, float(row["value"])))
    return points
