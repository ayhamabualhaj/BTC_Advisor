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


def monthly_changes(index_values):
    return [(later / earlier - 1) * 100 for earlier, later in zip(index_values, index_values[1:])]


def cpi_surprise(cpi_values, baseline_months=3):
    """Latest monthly CPI change minus the average of the previous few months.

    Consensus forecasts are not freely available, so the recent trend stands in for the
    expectation: negative means inflation came in cooler than the trend.
    """
    changes = monthly_changes(cpi_values)
    if len(changes) < baseline_months + 1:
        return None
    baseline = sum(changes[-(baseline_months + 1):-1]) / baseline_months
    return changes[-1] - baseline


def yoy_inflation(cpi_values):
    if len(cpi_values) < 13:
        return None
    return (cpi_values[-1] / cpi_values[-13] - 1) * 100
