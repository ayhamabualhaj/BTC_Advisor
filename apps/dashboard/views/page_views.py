import datetime

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ai.opus_client import model_label
from apps.agents.models import AgentName
from apps.backtest.services import combining_service, daily_run_service
from apps.dashboard.services import model_service, profit_service, report_service, signal_service

AGENT_ORDER = AgentName.values


def today(request, advice=None):
    context = report_service.today()
    runs = {run.agent: run for run in context["agent_runs"]}
    context["cards"] = [(agent, runs.get(agent)) for agent in AGENT_ORDER]
    decision = context["decision"]
    context["decision_rule_text"] = combining_service.describe(decision.rule) if decision and decision.rule else ""
    context["advice"] = advice
    return render(request, "dashboard/today.html", context)


@require_POST
def advise(request):
    """The "What should I do?" button: runs yesterday's agents if they have not run yet."""
    return today(request, daily_run_service.advice())


def agent_detail(request, agent):
    if agent not in AGENT_ORDER:
        raise Http404("Unknown agent")
    is_backtest = request.GET.get("backtest") == "1"
    history = report_service.agent_history(agent, is_backtest)
    chart = {
        "labels": [run.date for run in history],
        "rule": [run.rule_score for run in history],
        "ml": [run.ml_score for run in history],
        "opus": [run.opus_score for run in history],
        "llm_label": model_label(),
    }
    return render(request, "dashboard/agent.html", {
        "agent": agent,
        "label": AgentName(agent).label,
        "latest": history[-1] if history else None,
        "history": list(reversed(history))[:30],
        "is_backtest": is_backtest,
        "chart": chart,
    })


def parse_month(value):
    """"2024-05" -> date(2024, 5, 1); anything else -> None (the latest month)."""
    try:
        return datetime.date.fromisoformat(f"{value}-01") if value else None
    except ValueError:
        return None


def parse_horizon(request):
    try:
        horizon = int(request.GET.get("horizon", signal_service.DEFAULT_HORIZON))
    except ValueError:
        return signal_service.DEFAULT_HORIZON
    return horizon if horizon in signal_service.HORIZONS else signal_service.DEFAULT_HORIZON


def column_groups(columns):
    """Header groups: one per agent (its Rules, ML and LLM columns), then the vote."""
    groups = []
    for column in columns:
        if not groups or groups[-1]["agent"] != column.agent:
            groups.append({"agent": column.agent, "label": column.label, "span": 0})
        groups[-1]["span"] += 1
    return groups


def years(months):
    by_year = {}
    for month in months:
        by_year.setdefault(month.year, []).append(month)
    return sorted(by_year.items(), reverse=True)


def signals(request):
    horizon = parse_horizon(request)
    table = signal_service.month_table(parse_month(request.GET.get("month")), horizon)
    columns = table["columns"]
    for row in table["rows"]:
        row["cells"] = [(column, row["calls"][column.key]) for column in columns]
    # One scoreboard card per agent (plus the vote), one line per source.
    cards = {}
    for column in columns:
        cards.setdefault(column.agent, {"agent": column.agent, "label": column.label, "lines": []})
        cards[column.agent]["lines"].append({"column": column, **table["summary"].get(column.key, {})})
    return render(request, "dashboard/signals.html", {
        **table, "cards": list(cards.values()), "groups": column_groups(columns), "horizon": horizon,
        "horizons": signal_service.HORIZONS, "years": years(table["months"]), "sources": signal_service.sources(),
    })


def signals_overview(request):
    horizon = parse_horizon(request)
    data = signal_service.overview(horizon)
    columns = data["columns"]
    for entry in data["months"] + data["periods"]:
        entry["cells"] = [(column, entry["summary"][column.key]) for column in columns]
    return render(request, "dashboard/signals_overview.html", {
        **data, "groups": column_groups(columns), "horizon": horizon, "horizons": signal_service.HORIZONS,
        "sources": signal_service.sources(),
    })


def models(request):
    horizon = parse_horizon(request)
    data = model_service.comparison(request.GET.get("model"), horizon)
    return render(request, "dashboard/models.html", {**data, "horizon": horizon, "horizons": signal_service.HORIZONS})


def parse_date(value):
    try:
        return datetime.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def profit(request):
    data = profit_service.profit_page(request.GET.get("period"), parse_date(request.GET.get("start")),
                                      parse_date(request.GET.get("end")), request.GET.get("short") == "1")
    groups = [{"agent": agent.value, "label": agent.label} for agent in AgentName] + [{"agent": "vote", "label": "Votes"}]
    return render(request, "dashboard/profit.html", {**data, "groups": groups, "sources": signal_service.sources()})


def backtests(request):
    groups = report_service.backtest_overview()
    for run in groups["combining"]:
        run.periods = [("Chosen on (2019-2024)", run.settings["tuning"]), (f"Test ({run.start_date} on)", run.settings["test"])]
        run.rule_text = combining_service.describe(run.settings)
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
