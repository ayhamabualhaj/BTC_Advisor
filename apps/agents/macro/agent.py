"""Macro agent: its Opus input and its Opus call."""

from pathlib import Path

from apps.agents.ai import runner
from apps.agents.models import AgentName

AGENT = AgentName.MACRO
PROMPT_FILE = Path(__file__).with_name("prompt.md")
FED_MOVES = {1: "hike", -1: "cut", 0: "none"}


def model_input(snapshot):
    """Changes and spreads rather than levels, which would date the data."""
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


def run(date, client=None, is_backtest=False):
    return runner.run_agent(AGENT, PROMPT_FILE, model_input, date, client, is_backtest)
