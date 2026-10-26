"""Financial stress setup: how scared US stock and bond markets are."""


def model_input(snapshot):
    """VIX is a level, but one with the same meaning in any year (it never dates the data)."""
    return {
        "vix": snapshot.get("vix"),
        "vix_change_20d": snapshot.get("vix_change_20d"),
        "move_change_20d_pct": snapshot.get("move_change_20d_pct"),
        "nfci": snapshot.get("nfci"),
    }
