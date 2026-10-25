"""The morning routine: collect data, run the agents, decide, update outcomes."""

import datetime
from dataclasses import dataclass, field

from django.conf import settings

from apps.agents.models import AgentRun
from apps.agents.services import agent_service, rule_scoring_service
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
    if report.used_opus:
        report.agent_runs = agent_service.run_agents(date, client=client)
    else:
        rule_scoring_service.run_rules(date, save=True)
        report.agent_runs = list(AgentRun.objects.filter(date=date, is_backtest=False))

    report.decision = decision_service.make_decision(date)
    report.outcomes_updated = outcome_service.update_outcomes()
    return report
