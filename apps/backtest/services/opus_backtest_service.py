"""Runs the Opus agents day by day over a past period, within a spending cap."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Avg

from apps.agents.ai import prompts
from apps.agents.models import AgentRun
from apps.agents.services.agent_service import AGENT_MODULES

# Used for estimates until real runs exist. Measured in October 2026 at effort "medium":
# about 2,300 input and 300 output tokens, $0.016 per call.
DEFAULT_COST_PER_CALL = Decimal("0.016")


@dataclass
class OpusBacktestProgress:
    calls: int = 0
    spent_usd: Decimal = Decimal("0")
    errors: list = field(default_factory=list)
    stopped_at_cap: bool = False


def prompt_versions(agents):
    return {agent: prompts.current_version(agent, AGENT_MODULES[agent].PROMPT_FILE) for agent in agents}


def pending_days(agent, prompt_version, days):
    """Days without a successful backtest run for this prompt version, so reruns resume."""
    done = set(
        AgentRun.objects.filter(agent=agent, prompt_version=prompt_version, is_backtest=True,
                                opus_score__isnull=False, date__in=days)
        .values_list("date", flat=True)
    )
    return [day for day in days if day not in done]


def average_cost_per_call():
    average = AgentRun.objects.filter(cost_usd__gt=0).aggregate(avg=Avg("cost_usd"))["avg"]
    return Decimal(str(average)) if average else DEFAULT_COST_PER_CALL


def estimate(agents, days):
    versions = prompt_versions(agents)
    calls = sum(len(pending_days(agent, versions[agent], days)) for agent in agents)
    return calls, calls * average_cost_per_call()


def run(agents, days, max_cost_usd, client=None, on_run=None):
    """Each agent on its own, oldest day first. Stops before a call that could pass the cap."""
    progress = OpusBacktestProgress()
    versions = prompt_versions(agents)
    per_call = average_cost_per_call()
    for agent in agents:
        for day in pending_days(agent, versions[agent], days):
            if progress.spent_usd + per_call > max_cost_usd:
                progress.stopped_at_cap = True
                return progress
            agent_run = AGENT_MODULES[agent].run(day, client, is_backtest=True)
            progress.calls += 1
            progress.spent_usd += agent_run.cost_usd
            # Keep the estimate honest as real costs come in.
            per_call = progress.spent_usd / progress.calls
            if agent_run.error:
                progress.errors.append(f"{day} {agent}: {agent_run.error}")
            if on_run:
                on_run(agent_run)
    return progress
