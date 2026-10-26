"""Risk-on day setup: today's move of Bitcoin and of the Nasdaq."""


def model_input(snapshot):
    return {
        "btc_change_1d_pct": snapshot.get("btc_change_1d_pct"),
        "nasdaq_change_1d_pct": snapshot.get("nasdaq_change_1d_pct"),
    }
