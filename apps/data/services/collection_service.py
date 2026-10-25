import datetime
from dataclasses import dataclass, field

from apps.data.collectors import binance, bybit, fred, okx_liquidations, yahoo
from apps.data.collectors.base import CollectorError
from apps.data.repositories import market_data_repository

COLLECTORS = {
    binance.SOURCE: binance,
    bybit.SOURCE: bybit,
    okx_liquidations.SOURCE: okx_liquidations,
    yahoo.SOURCE: yahoo,
    fred.SOURCE: fred,
}

# Crypto trades every day; stock indexes and FRED series only on business days.
EVERY_DAY_SOURCES = {binance.SOURCE, bybit.SOURCE, okx_liquidations.SOURCE}
# Monthly or event-driven fields where gaps are normal.
SPARSE_FIELDS = {"cpi", "core_cpi"}


@dataclass
class CollectionResult:
    saved: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)


def collect(start, end, sources=None):
    """Run each collector and save its points. One failing source does not stop the others."""
    result = CollectionResult()
    for source in sources or COLLECTORS:
        try:
            points = COLLECTORS[source].collect(start, end)
        except CollectorError as error:
            result.errors[source] = str(error)
            continue
        result.saved[source] = market_data_repository.save_points(source, points)
    return result


def expected_days(source, start, end):
    days = [start + datetime.timedelta(days=n) for n in range((end - start).days + 1)]
    if source in EVERY_DAY_SOURCES:
        return days
    if source == fred.SOURCE:
        # FRED values are dated one day late (see fred.py), so business days land Tue-Sat.
        return [day for day in days if (day - datetime.timedelta(days=1)).weekday() < 5]
    return [day for day in days if day.weekday() < 5]


def missing_days(start, end, sources=None):
    """Return {(source, field): [missing dates]} for every field that has gaps.

    Business-day sources will also list US market holidays; those gaps are expected.
    """
    gaps = {}
    for source in sources or COLLECTORS:
        for field_name in market_data_repository.fields_for(source):
            if field_name in SPARSE_FIELDS:
                continue
            have = market_data_repository.dates_for(source, field_name, start, end)
            # Only check from the first stored day: some series (liquidations) start late.
            first = min(have, default=None)
            if first is None:
                continue
            missing = [day for day in expected_days(source, first, end) if day not in have]
            if missing:
                gaps[(source, field_name)] = missing
    return gaps
