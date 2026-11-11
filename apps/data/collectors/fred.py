"""US rates, inflation, VIX and financial conditions from the FRED API (free key in FRED_API_KEY)."""

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
    # Gold's macro agent: the 10-year yield and the 10-year yield after expected inflation (TIPS).
    "DGS10": "treasury_10y",
    "DFII10": "real_yield_10y",
}
# Weekly and monthly series are revised after release (CPI's seasonal factors every February
# for five years back, NFCI every week for its whole history), so they are taken as first
# published (ALFRED's initial release) and dated by the publication day: a backtest then
# sees only what was known that day. Both come out at 8:30 New York time.
FIRST_RELEASE_SERIES = {
    "CPIAUCSL": "cpi",
    "CPILFESL": "core_cpi",
    "NFCI": "nfci",
}
# Monthly series also store which month each print measures, as YYYYMM in "<field>_month" on
# the same day: the prints are not always consecutive months (October 2025 was never published).
MONTHLY_FIELDS = {"cpi", "core_cpi"}
MONTH_SUFFIX = "_month"
# Fetch a year earlier so year-over-year inflation can be computed.
FIRST_RELEASE_HISTORY = datetime.timedelta(days=400)


def collect(start, end):
    if not settings.FRED_API_KEY:
        raise CollectorError("FRED_API_KEY is not set in .env (free key from fred.stlouisfed.org)")
    points = []
    for series, field in DAILY_SERIES.items():
        points.extend(parse_daily(fetch_observations(series, start, end), field))
    for series, field in FIRST_RELEASE_SERIES.items():
        observations = fetch_first_releases(series, start - FIRST_RELEASE_HISTORY, end)
        points.extend(parse_first_release(observations, field))
        if field in MONTHLY_FIELDS:
            points.extend(observation_months(observations, field))
    return [p for p in points if p.date <= end]


def call(path, **params):
    return get_json(f"{URL}/{path}", {**params, "api_key": settings.FRED_API_KEY, "file_type": "json"})


def fetch_observations(series, start, end):
    return call("series/observations", series_id=series,
                observation_start=start.isoformat(), observation_end=end.isoformat())["observations"]


def fetch_first_releases(series, start, end):
    """Each observation's value as first published, with its publication day (realtime_start)."""
    return call("series/observations", series_id=series, observation_start=start.isoformat(),
                observation_end=end.isoformat(), realtime_start="1776-07-04", realtime_end="9999-12-31",
                output_type=4)["observations"]


def parse_daily(observations, field):
    points = []
    for row in observations:
        if row["value"] == ".":
            continue  # FRED's marker for a missing day
        day = datetime.date.fromisoformat(row["date"]) + datetime.timedelta(days=1)
        points.append(Point(day, field, float(row["value"])))
    return points


def parse_first_release(observations, field):
    """Sometimes several observations come out the same day (NFCI after holidays). A day holds
    one value, so each later one moves to the next free day: a day late, never early. A month
    with no value (October 2025 CPI, never published) is skipped."""
    points = []
    for row in sorted(observations, key=lambda row: row["date"]):
        if row["value"] == ".":
            continue
        day = datetime.date.fromisoformat(row["realtime_start"])
        if points and day <= points[-1].date:
            day = points[-1].date + datetime.timedelta(days=1)
        points.append(Point(day, field, float(row["value"])))
    return points


def observation_months(observations, field):
    """The month each print measures, as YYYYMM, on the day its value is stored."""
    values = parse_first_release(observations, field)
    published = sorted((row for row in observations if row["value"] != "."), key=lambda row: row["date"])
    return [Point(point.date, field + MONTH_SUFFIX, float(row["date"][:7].replace("-", "")))
            for point, row in zip(values, published)]
