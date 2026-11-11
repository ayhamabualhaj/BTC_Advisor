"""Fills in what the price did after each live decision, and whether each agent was right."""

import datetime

from ai import domains
from apps.agents.models import AgentRun
from apps.backtest.calibration import HORIZON_DAYS, later_close
from apps.backtest.models import Decision, Outcome
from apps.backtest.repositories import price_repository
from apps.data import assets


def decision_dates():
    live = AgentRun.objects.filter(is_backtest=False, agent__in=domains.agents()).values_list("date", flat=True)
    return sorted(set(live) | set(Decision.objects.filter(asset=assets.current().key).values_list("date", flat=True)))


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
    """Create or refresh the current asset's Outcome of every decision date; returns how many were saved."""
    asset = assets.current()
    dates = decision_dates()
    if not dates:
        return 0
    wait = asset.outcome_wait_days
    closes = price_repository.closes(dates[0], dates[-1] + datetime.timedelta(days=HORIZON_DAYS + wait))
    saved = 0
    for date in dates:
        if date not in closes:
            continue
        price = closes[date]
        later = {days: later_close(closes, date, days, wait) for days in (1, 3, HORIZON_DAYS)}
        change_7d = later[HORIZON_DAYS] / price - 1 if later[HORIZON_DAYS] else None
        Outcome.objects.update_or_create(date=date, asset=asset.key, defaults={
            "price_at_decision": price,
            "price_after_1d": later[1],
            "price_after_3d": later[3],
            "price_after_7d": later[HORIZON_DAYS],
            **{f"{asset.domain(agent)}_correct": agent_correct(date, agent, change_7d) for agent in domains.agents()},
        })
        saved += 1
    return saved
