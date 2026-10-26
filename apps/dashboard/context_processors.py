from ai.opus_client import model_label


def llm(request):
    """The name of the Claude model the agents ask (AI_MODEL), e.g. "Haiku 5.5", on every page."""
    return {"llm_label": model_label()}
