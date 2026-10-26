import datetime
from urllib.parse import urlencode

from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ai.opus_client import model_label
from apps.agents.models import AgentName
from apps.backtest.services import combining_service, daily_run_service
from apps.dashboard.services import model_service, profit_service, report_service, signal_service

AGENT_ORDER = AgentName.values


def today(request, advice=None):
    context = report_service.today()
    runs = {run.agent: run for run in context["agent_runs"]}
    context["cards"] = [(agent, AgentName(agent).label, runs.get(agent)) for agent in AGENT_ORDER]
    decision = context["decision"]
    context["decision_rule_text"] = combining_service.describe(decision.rule) if decision and decision.rule else ""
    context["advice"] = advice
    # The vote shown is the advice's when the button was pressed, else the latest decision's.
    shown = advice.decision if advice and advice.decision else decision
    context["breakdown"] = report_service.vote_breakdown(shown) if shown and shown.group_calls else None
    return render(request, "dashboard/today.html", context)


@require_POST
def advise(request):
    """The "What should I do?" button: runs yesterday's agents if they have not run yet."""
    return today(request, daily_run_service.advice())


def agents(request):
    """The Agents menu link: opens the first agent's tab."""
    return redirect("agent_detail", AGENT_ORDER[0])


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
        "tabs": [(choice.value, choice.label) for choice in AgentName],
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


def profit_links(data):
    """Each control's link: the page's current settings with one of them changed."""
    current = {"period": data["preset"] if data.get("preset") != "custom" else None,
               "start": data["start"].isoformat() if data.get("preset") == "custom" else None,
               "end": data["end"].isoformat() if data.get("preset") == "custom" else None,
               "short": "1" if data["short"] else None, "days": str(data["hold_days"]) if data["hold_days"] != 1 else None,
               "between": "hold" if data["hold_between"] else None}

    def link(**changes):
        return "?" + urlencode({key: value for key, value in {**current, **changes}.items() if value})

    return {
        "periods": [(key, label, link(period=key, start=None, end=None)) for key, label in data["presets"]],
        "sell": [(False, "Stay out", link(short=None)), (True, "Go short", link(short="1"))],
        "days": [(days, link(days=str(days) if days != 1 else None)) for days in profit_service.HOLD_DAYS],
        "between": [(False, "Stay out", link(between=None)), (True, "Hold Bitcoin", link(between="hold"))],
        "hidden": {key: current[key] for key in ("short", "days", "between") if current[key]},
    }


def profit(request):
    try:
        days = int(request.GET.get("days", 1))
    except ValueError:
        days = 1
    data = profit_service.profit_page(request.GET.get("period"), parse_date(request.GET.get("start")),
                                      parse_date(request.GET.get("end")), request.GET.get("short") == "1",
                                      days, request.GET.get("between") == "hold")
    groups = [{"agent": agent.value, "label": agent.label} for agent in AgentName] + [{"agent": "vote", "label": "Votes"}]
    links = profit_links(data) if "preset" in data else None
    return render(request, "dashboard/profit.html",
                  {**data, "groups": groups, "sources": signal_service.sources(), "links": links})


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
