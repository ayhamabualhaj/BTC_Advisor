"""The model input as prompt v2 saw it, kept so v2 can be re-tested against v3 on equal
terms (compare_prompts). Live runs never use it."""

from ai.derivatives import inputs as derivatives_inputs
from ai.macro.inputs import FED_MOVES
from ai.technical import inputs as technical_inputs


def macro(snapshot):
    nasdaq, nasdaq_sma = snapshot.get("nasdaq"), snapshot.get("nasdaq_sma_50")
    two_year, fed_funds = snapshot.get("treasury_2y"), snapshot.get("fed_funds_effective")
    return {
        "dollar_index_change_2w_pct": snapshot.get("dxy_change_2w_pct"),
        "nasdaq_vs_sma_50_pct": round((nasdaq / nasdaq_sma - 1) * 100, 2) if nasdaq and nasdaq_sma else None,
        "fed_last_move_60d": FED_MOVES.get(snapshot.get("fed_rate_change_60d")),
        "two_year_minus_fed_funds_pct": round(two_year - fed_funds, 2)
        if two_year is not None and fed_funds is not None else None,
        "cuts_expected": snapshot.get("cuts_expected"),
        "cpi_yoy_pct": snapshot.get("cpi_yoy_pct"),
        "cpi_surprise_pct": snapshot.get("cpi_surprise_pct"),
        "spot_fund_net_flow_5d_musd": snapshot.get("etf_net_flow_5d_musd"),
    }


def derivatives(snapshot):
    setup = derivatives_inputs.model_input(snapshot)
    setup.pop("funding_rate_30d_avg_pct")
    return setup


MODEL_INPUTS = {"technical": technical_inputs.model_input, "derivatives": derivatives, "macro": macro}
