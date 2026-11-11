"""Gold's macro setup as relative numbers: the dollar, yields, the Fed, inflation, stocks."""

from ai.macro.inputs import FED_MOVES


def model_input(snapshot):
    """Changes and spreads rather than levels, which would date the data. The real yield is a
    level, but one that means the same in any year."""
    nasdaq, nasdaq_sma = snapshot.get("nasdaq"), snapshot.get("nasdaq_sma_50")
    two_year, fed_funds = snapshot.get("treasury_2y"), snapshot.get("fed_funds_effective")
    return {
        "dollar_index_change_2w_pct": snapshot.get("dxy_change_2w_pct"),
        "dollar_index_change_1m_pct": snapshot.get("dxy_change_1m_pct"),
        "real_yield_10y_pct": snapshot.get("real_yield_10y"),
        "real_yield_10y_change_5d": snapshot.get("real_yield_10y_change_5d"),
        "real_yield_10y_change_20d": snapshot.get("real_yield_10y_change_20d"),
        "ten_year_change_20d": snapshot.get("treasury_10y_change_20d"),
        "two_year_change_20d": snapshot.get("treasury_2y_change_20d"),
        "two_year_minus_fed_funds_pct": round(two_year - fed_funds, 2)
        if two_year is not None and fed_funds is not None else None,
        "fed_last_move_60d": FED_MOVES.get(snapshot.get("fed_rate_change_60d")),
        "cpi_yoy_pct": snapshot.get("cpi_yoy_pct"),
        "cpi_surprise_pct": snapshot.get("cpi_surprise_pct"),
        "nasdaq_vs_sma_50_pct": round((nasdaq / nasdaq_sma - 1) * 100, 2) if nasdaq and nasdaq_sma else None,
        "nasdaq_change_5d_pct": snapshot.get("nasdaq_change_5d_pct"),
        "nasdaq_change_20d_pct": snapshot.get("nasdaq_change_20d_pct"),
        "sp500_change_20d_pct": snapshot.get("sp500_change_20d_pct"),
    }
