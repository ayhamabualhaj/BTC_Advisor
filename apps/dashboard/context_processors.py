from ai.opus_client import model_label
from apps.backtest.repositories import price_repository


def llm(request):
    """The name of the Claude model the agents ask (AI_MODEL), e.g. "Haiku 5.5", on every page."""
    return {"llm_label": model_label()}


def freshness(request):
    """The day of the last stored Bitcoin close, for the footer of every page."""
    return {"prices_to": price_repository.latest_close_date()}
