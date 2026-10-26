"""Fills in what the price did after each live decision, and whether each agent was right."""

import datetime

from apps.agents.models import AgentName, AgentRun
from apps.backtest.calibration import HORIZON_DAYS
from apps.backtest.models import Decision, Outcome
from apps.backtest.repositories import price_repository


def decision_dates():
    live = AgentRun.objects.filter(is_backtest=False).values_list("date", flat=True)
    return sorted(set(live) | set(Decision.objects.values_list("date", flat=True)))


def agent_correct(date, agent, change_7d):
    """Right if the score's side (above or below 50) matched the 7-day move."""
    run = AgentRun.objects.filter(date=date, agent=agent, is_backtest=False).order_by("-created_at").first()
    if run is None or change_7d is None or change_7d == 0:
        return None
    score = next((s for s in (run.opus_score, run.rule_score, run.ml_score) if s is not None), None)
    if score is None or score == 50:
        return None
    return (score > 50) == (change_7d > 0)


def update_outcomes():
    """Create or refresh the Outcome of every decision date; returns how many were saved."""
    dates = decision_dates()
    if not dates:
        return 0
    closes = price_repository.closes(dates[0], dates[-1] + datetime.timedelta(days=HORIZON_DAYS))
    saved = 0
    for date in dates:
        if date not in closes:
            continue
        price = closes[date]
        later = {days: closes.get(date + datetime.timedelta(days=days)) for days in (1, 3, HORIZON_DAYS)}
        change_7d = later[HORIZON_DAYS] / price - 1 if later[HORIZON_DAYS] else None
        Outcome.objects.update_or_create(date=date, defaults={
            "price_at_decision": price,
            "price_after_1d": later[1],
            "price_after_3d": later[3],
            "price_after_7d": later[HORIZON_DAYS],
            **{f"{agent}_correct": agent_correct(date, agent, change_7d) for agent in AgentName.values},
        })
        saved += 1
    return saved
