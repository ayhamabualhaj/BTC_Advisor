"""Gold's dollar setup: how the dollar index has moved, and how gold has moved against it."""


def model_input(snapshot):
    """Moves and a correlation only: no level of the index or of the price."""
    return {
        "dxy_change_5d_pct": snapshot.get("dxy_change_5d_pct"),
        "dxy_change_20d_pct": snapshot.get("dxy_change_20d_pct"),
        "dxy_change_60d_pct": snapshot.get("dxy_change_60d_pct"),
        "dxy_vs_sma_50_pct": snapshot.get("dxy_vs_sma_50_pct"),
        "gold_minus_dxy_20d_pct": snapshot.get("gold_minus_dxy_20d_pct"),
        "gold_dxy_correlation_60d": snapshot.get("gold_dxy_correlation_60d"),
    }
