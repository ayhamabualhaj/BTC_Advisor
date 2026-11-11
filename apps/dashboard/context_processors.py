from ai.opus_client import model_label
from apps.backtest.repositories import price_repository
from apps.data import assets


def llm(request):
    """The name of the Claude model the agents ask (AI_MODEL), e.g. "Haiku 5.5", on every page."""
    return {"llm_label": model_label()}


def freshness(request):
    """The day of the page's market's last stored close, for the footer of every page."""
    return {"prices_to": price_repository.latest_close_date()}


def market(request):
    """The market the page is about (the pages run inside assets.use) and all of them, for the switch."""
    return {"asset": assets.current(), "assets": list(assets.ASSETS.values())}
