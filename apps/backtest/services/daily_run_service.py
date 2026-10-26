"""The morning routine: collect data, run the agents, decide, update outcomes."""

import datetime
from dataclasses import dataclass, field

from django.conf import settings

from apps.agents.models import AgentRun
from apps.backtest.decision_rule import overall_call
from apps.backtest.models import Decision
from ai.domains import DOMAINS, with_kind
from apps.agents.services import agent_service, memory_service
from apps.backtest.repositories import price_repository
from apps.backtest.services import decision_service, outcome_service
from apps.data.services import collection_service

# Re-collect this many recent days every morning, so a missed day fills itself in.
COLLECT_DAYS = 10


class DailyRunError(Exception):
    pass


@dataclass
class DailyRunReport:
    date: datetime.date
    collection_errors: dict = field(default_factory=dict)
    used_opus: bool = False
    agent_runs: list = field(default_factory=list)
    decision: object = None
    outcomes_updated: int = 0
    memory_cases: int = 0


def last_full_day():
    return datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)


def already_ran(date):
    return AgentRun.objects.filter(date=date, is_backtest=False).exists()


def run(date=None, rules_only=False, force=False, client=None, collect=True):
    date = date or last_full_day()
    if already_ran(date) and not force:
        raise DailyRunError(f"Agents already ran for {date}; use --force to run (and pay) again.")
    report = DailyRunReport(date=date)

    if collect:
        result = collection_service.collect(date - datetime.timedelta(days=COLLECT_DAYS - 1), date)
        report.collection_errors = result.errors
    if date not in price_repository.closes(date, date):
        raise DailyRunError(f"No BTC close for {date} yet; the daily candle may not be final.")

    # Without credentials there is nothing to call, so fall back to the free rule scores.
    report.used_opus = not rules_only and bool(settings.ANTHROPIC_API_KEY or client)
    report.agent_runs = agent_service.run_agents(date, use_opus=report.used_opus, client=client)

    report.decision = decision_service.make_decision(date)
    report.outcomes_updated = outcome_service.update_outcomes()
    # Days whose 7-day outcome became known recently join the memory.
    for agent in with_kind("ml"):
        report.memory_cases += memory_service.build_cases(
            agent, DOMAINS[agent].inputs.model_input, date - datetime.timedelta(days=COLLECT_DAYS + 7), date)
    return report


@dataclass
class Advice:
    date: datetime.date
    call: str = "none"  # "buy", "sell", "hold" or "none" (could not decide)
    decision: object = None
    error: str = ""


def advice():
    """The overall call for the last full day, running the day first if it has not run.

    A day that already ran is only read back, so asking again never pays twice.
    """
    date = last_full_day()
    decision = Decision.objects.filter(date=date).order_by("-created_at").first()
    try:
        if decision is None and already_ran(date):
            decision = decision_service.make_decision(date)
        elif decision is None:
            decision = run(date).decision
    except DailyRunError as error:
        return Advice(date=date, error=str(error))
    return Advice(date=date, call=overall_call(decision.group_calls), decision=decision)
