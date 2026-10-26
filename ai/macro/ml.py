"""Macro ML agent: a random forest on the past month's macro moves, retrained monthly.

It gets more numbers than the Opus input: one-month dollar and two-year-yield changes,
5- and 20-day Nasdaq and 20-day S&P moves. Spot-fund flows (only since 2024) and
"cuts expected" (a yes/no version of the spread) are left out.
"""

from ai import ml, similarity

from .inputs import FED_MOVES


def features(snapshot, setup):
    numbers = {
        "dollar_index_change_2w_pct": snapshot.get("dxy_change_2w_pct"),
        "dollar_index_change_1m_pct": snapshot.get("dxy_change_1m_pct"),
        "nasdaq_vs_sma_50_pct": setup.get("nasdaq_vs_sma_50_pct"),
        "nasdaq_change_5d_pct": snapshot.get("nasdaq_change_5d_pct"),
        "nasdaq_change_20d_pct": snapshot.get("nasdaq_change_20d_pct"),
        "sp500_change_20d_pct": snapshot.get("sp500_change_20d_pct"),
        "fed_last_move_60d": FED_MOVES.get(snapshot.get("fed_rate_change_60d")),
        "two_year_minus_fed_funds_pct": setup.get("two_year_minus_fed_funds_pct"),
        "two_year_change_20d": snapshot.get("treasury_2y_change_20d"),
        "cpi_yoy_pct": snapshot.get("cpi_yoy_pct"),
        "cpi_surprise_pct": snapshot.get("cpi_surprise_pct"),
    }
    return similarity.encode(numbers)


def training_cutoff(date):
    # Retrained once a month, as it was tested: one forest per month instead of per day.
    return ml.monthly_cutoff(date)


def score(brief):
    cutoff = training_cutoff(brief.date)
    return ml.score(brief.ml_features, brief.training, build=ml.forest, cache_key=("macro", cutoff))
