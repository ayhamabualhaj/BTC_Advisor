"""Derivatives agent: its Opus input and its Opus call."""

from pathlib import Path

from apps.agents.ai import runner
from apps.agents.models import AgentName

AGENT = AgentName.DERIVATIVES
PROMPT_FILE = Path(__file__).with_name("prompt.md")


def scaled(value, factor, digits):
    return None if value is None else round(value * factor, digits)


def model_input(snapshot):
    return {
        "funding_rate_8h_pct": scaled(snapshot.get("funding_rate"), 100, 4),
        "funding_rate_7d_avg_pct": scaled(snapshot.get("funding_rate_7d_avg"), 100, 4),
        "open_interest_change_3d_pct": scaled(snapshot.get("open_interest_change_3d_pct"), 1, 2),
        "price_change_3d_pct": scaled(snapshot.get("price_change_3d_pct"), 1, 2),
        "long_account_share": snapshot.get("long_account_ratio"),
        "long_account_share_90d_avg": scaled(snapshot.get("long_account_ratio_90d_avg"), 1, 3),
        "long_liquidations_musd_1d": scaled(snapshot.get("long_liquidations_usd_1d"), 1e-6, 2),
        "long_liquidations_musd_3d_avg": scaled(snapshot.get("long_liquidations_usd_3d_avg"), 1e-6, 2),
        "short_liquidations_musd_1d": scaled(snapshot.get("short_liquidations_usd_1d"), 1e-6, 2),
    }


def run(date, client=None, is_backtest=False):
    return runner.run_agent(AGENT, PROMPT_FILE, model_input, date, client, is_backtest)
