from django.http import Http404
from django.shortcuts import render

from apps.agents.models import AgentName
from apps.backtest.services import combining_service
from apps.dashboard.services import report_service

AGENT_ORDER = AgentName.values


def today(request):
    context = report_service.today()
    runs = {run.agent: run for run in context["agent_runs"]}
    context["cards"] = [(agent, runs.get(agent)) for agent in AGENT_ORDER]
    context["rule"] = combining_service.current_rule()
    return render(request, "dashboard/today.html", context)


def agent_detail(request, agent):
    if agent not in AGENT_ORDER:
        raise Http404("Unknown agent")
    is_backtest = request.GET.get("backtest") == "1"
    history = report_service.agent_history(agent, is_backtest)
    chart = {
        "labels": [run.date for run in history],
        "rule": [run.rule_score for run in history],
        "opus": [run.opus_score for run in history],
    }
    return render(request, "dashboard/agent.html", {
        "agent": agent,
        "label": AgentName(agent).label,
        "latest": history[-1] if history else None,
        "history": list(reversed(history))[:30],
        "is_backtest": is_backtest,
        "chart": chart,
    })


def backtests(request):
    groups = report_service.backtest_overview()
    chart = {
        "labels": [run.name for run in groups["strategies"]],
        "profit": [round(run.total_profit_pct or 0, 2) for run in groups["strategies"]],
        "hold": groups["strategies"][0].buy_and_hold_pct if groups["strategies"] else None,
    }
    return render(request, "dashboard/backtests.html", {**groups, "chart": chart})


def costs(request):
    data = report_service.costs()
    for row in data["by_agent"]:
        row["per_call"] = row["cost_usd"] / row["calls"]
    days = sorted({row["day"] for row in data["by_day"]})
    per_agent = {agent: [0.0] * len(days) for agent in AGENT_ORDER}
    for row in data["by_day"]:
        per_agent[row["agent"]][days.index(row["day"])] = float(row["cost_usd"])
    chart = {"labels": days, "series": [{"agent": agent, "values": per_agent[agent]} for agent in AGENT_ORDER]}
    return render(request, "dashboard/costs.html", {**data, "chart": chart})


def prompts(request):
    return render(request, "dashboard/prompts.html", {"history": report_service.prompt_history()})
