"""The Model comparison page: AI_MODEL (Opus) and another Claude model on the same saved
questions, per agent, judged like the Signals page."""

from django.conf import settings

from apps.agents.models import AgentName
from apps.backtest.services import model_comparison_service as mcs
from apps.dashboard.services.signal_service import score_call


def label(model):
    """"claude-haiku-5-5" -> "Haiku 5.5"."""
    parts = model.removeprefix("claude-").split("-")
    return f"{parts[0].capitalize()} {'.'.join(parts[1:])}".strip()


def day_rows(found, moves):
    """{agent: [row]} newest first, each row with both models' calls on the same question."""
    rows = {}
    for ref, other in found:
        move = moves.get(ref.date)
        reference_call, other_call = score_call(ref.opus_score, move), score_call(other.opus_score, move)
        rows.setdefault(ref.agent, []).append({
            "date": ref.date,
            "return_pct": move * 100 if move is not None else None,
            "reference": reference_call,
            "other": other_call,
            "same_side": reference_call.signal == other_call.signal,
            "gap": other.opus_score - ref.opus_score,
            "other_reasons": other.reasons,
            "reference_reasons": ref.reasons,
        })
    return {agent: list(reversed(agent_rows)) for agent, agent_rows in rows.items()}


def chart(found):
    """{agent: {"labels", "reference", "other"}} oldest first, for the score lines."""
    data = {}
    for ref, other in found:
        series = data.setdefault(ref.agent, {"labels": [], "reference": [], "other": []})
        series["labels"].append(ref.date.isoformat())
        series["reference"].append(ref.opus_score)
        series["other"].append(other.opus_score)
    return data


def comparison(model=None, horizon=7):
    models = mcs.compared_models()
    model = model if model in models else (models[0] if models else None)
    page = {"models": [(m, label(m)) for m in models], "model": model, "reference": settings.AI_MODEL,
            "reference_label": label(settings.AI_MODEL), "other_label": label(model) if model else ""}
    if model is None:
        return {**page, "agents": []}
    found = mcs.pairs(model)
    summary = mcs.compare(model, horizon, found)
    rows = day_rows(found, mcs.moves(found, horizon))
    agents = [{"key": agent.value, "label": agent.label, "summary": summary[agent.value],
               "rows": rows.get(agent.value, [])}
              for agent in AgentName if agent.value in summary]
    return {**page, "agents": agents, "total": summary.get("all"), "chart": chart(found)}
