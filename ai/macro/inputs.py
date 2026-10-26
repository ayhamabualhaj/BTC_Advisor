"""Macro setup as relative numbers: what the ML and Opus agents see."""

FED_MOVES = {1: "hike", -1: "cut", 0: "none"}


def model_input(snapshot):
    """Changes and spreads rather than levels, which would date the data."""
    nasdaq, nasdaq_sma = snapshot.get("nasdaq"), snapshot.get("nasdaq_sma_50")
    two_year, fed_funds = snapshot.get("treasury_2y"), snapshot.get("fed_funds_effective")
    return {
        "dollar_index_change_2w_pct": snapshot.get("dxy_change_2w_pct"),
        "dollar_index_change_1m_pct": snapshot.get("dxy_change_1m_pct"),
        "nasdaq_vs_sma_50_pct": round((nasdaq / nasdaq_sma - 1) * 100, 2) if nasdaq and nasdaq_sma else None,
        "nasdaq_change_5d_pct": snapshot.get("nasdaq_change_5d_pct"),
        "sp500_change_20d_pct": snapshot.get("sp500_change_20d_pct"),
        "fed_last_move_60d": FED_MOVES.get(snapshot.get("fed_rate_change_60d")),
        "two_year_minus_fed_funds_pct": round(two_year - fed_funds, 2)
        if two_year is not None and fed_funds is not None else None,
        "two_year_change_20d": snapshot.get("treasury_2y_change_20d"),
        "cpi_yoy_pct": snapshot.get("cpi_yoy_pct"),
        "cpi_surprise_pct": snapshot.get("cpi_surprise_pct"),
        "spot_fund_net_flow_5d_musd": snapshot.get("etf_net_flow_5d_musd"),
    }

