"""Technical-analysis agent: its Opus input and its Opus call."""

from pathlib import Path

from apps.agents.ai import runner
from apps.agents.models import AgentName

AGENT = AgentName.TECHNICAL
PROMPT_FILE = Path(__file__).with_name("prompt.md")


def pct_from(value, reference):
    if value is None or not reference:
        return None
    return round((value / reference - 1) * 100, 2)


def model_input(snapshot):
    """Relative numbers only: an absolute price would reveal the asset and the year."""
    close = snapshot.get("close")
    return {
        "price_vs_sma_20_pct": pct_from(close, snapshot.get("sma_20")),
        "price_vs_sma_50_pct": pct_from(close, snapshot.get("sma_50")),
        "price_vs_sma_200_pct": pct_from(close, snapshot.get("sma_200")),
        "sma_50_vs_sma_200_pct": pct_from(snapshot.get("sma_50"), snapshot.get("sma_200")),
        "rsi_14": snapshot.get("rsi_14"),
        "macd_cross_3d": snapshot.get("macd_cross_3d"),
        "change_7d_pct": snapshot.get("change_7d_pct"),
        "change_30d_pct": snapshot.get("change_30d_pct"),
        "support_distance_pct": -pct_from(snapshot.get("support"), close) if snapshot.get("support") else None,
        "resistance_distance_pct": pct_from(snapshot.get("resistance"), close),
    }


def run(date, client=None, is_backtest=False):
    return runner.run_agent(AGENT, PROMPT_FILE, model_input, date, client, is_backtest)
