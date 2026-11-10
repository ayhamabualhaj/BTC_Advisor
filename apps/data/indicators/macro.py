def last_rate_change(rates, within):
    """+1 if the policy rate was raised in the last `within` observations, -1 if cut, else 0."""
    recent = rates[-(within + 1):]
    for before, after in reversed(list(zip(recent, recent[1:]))):
        if after > before:
            return 1
        if after < before:
            return -1
    return 0


def cuts_expected(treasury_2y, fed_funds, margin=0.25):
    """The 2-year yield well below the policy rate means the market prices in cuts.

    A free stand-in for futures-implied odds, which have no free API.
    """
    if treasury_2y is None or fed_funds is None:
        return None
    return treasury_2y < fed_funds - margin


def month_number(yyyymm):
    """202511 -> a count of months, so two months in a row differ by exactly 1."""
    year, month = divmod(int(yyyymm), 100)
    return year * 12 + month


def every_month(observations):
    """[(month number, index value)], oldest first -> one value per month, first to last.

    The prints are not always consecutive months: October 2025 was never published (the
    government shutdown). A missing month is filled in at the steady rate between its
    neighbours, so a change over two months is never read as one month's change.
    """
    if not observations:
        return []
    values = []
    for (earlier_month, earlier), (later_month, later) in zip(observations, observations[1:]):
        months_apart = later_month - earlier_month
        values.extend(earlier * (later / earlier) ** (step / months_apart) for step in range(months_apart))
    return values + [observations[-1][1]]


def monthly_changes(index_values):
    return [(later / earlier - 1) * 100 for earlier, later in zip(index_values, index_values[1:])]


def cpi_surprise(observations, baseline_months=3):
    """Latest monthly CPI change minus the average of the previous few months.

    Consensus forecasts are not freely available, so the recent trend stands in for the
    expectation: negative means inflation came in cooler than the trend. `observations` are
    [(month number, index value)]; a print that covers two months counts at its monthly rate.
    """
    if len(observations) < 2:
        return None
    changes = monthly_changes(every_month(observations))
    # A print covering two months is one piece of news, so none of it belongs in the trend.
    months_in_latest = observations[-1][0] - observations[-2][0]
    baseline = changes[:-months_in_latest][-baseline_months:]
    if len(baseline) < baseline_months:
        return None
    return changes[-1] - sum(baseline) / baseline_months


def yoy_inflation(observations):
    """Change from the same month a year earlier (12 real months back, not 12 prints back)."""
    values = every_month(observations)
    if len(values) < 13:
        return None
    return (values[-1] / values[-13] - 1) * 100
