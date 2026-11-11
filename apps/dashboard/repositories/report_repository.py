from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from ai import domains
from apps.agents.models import AgentRun, PromptVersion
from apps.backtest.models import BacktestRun, Decision
from apps.data import assets

# Agent runs, decisions and backtests are read for the current asset (Bitcoin unless the code
# runs inside assets.use); money spent and prompts are listed for every asset together.


def latest_decision():
    return Decision.objects.filter(asset=assets.current().key).order_by("-date", "-created_at").first()


def latest_live_runs(date):
    """The newest live run of each agent on a date."""
    runs = {}
    for run in (AgentRun.objects.filter(date=date, is_backtest=False, agent__in=domains.agents())
                .select_related("prompt_version").order_by("created_at")):
        runs[run.agent] = run
    return list(runs.values())


def latest_live_date():
    run = AgentRun.objects.filter(is_backtest=False, agent__in=domains.agents()).order_by("-date").first()
    return run.date if run else None


def agent_runs(agent=None, is_backtest=None, date=None):
    runs = AgentRun.objects.select_related("prompt_version").order_by("-date", "-created_at")
    if agent:
        runs = runs.filter(agent=agent)
    if is_backtest is not None:
        runs = runs.filter(is_backtest=is_backtest)
    if date:
        runs = runs.filter(date=date)
    return runs


def backtest_runs(name_prefix=None):
    # Another asset's runs carry its key in front of the name (assets.Asset.named).
    others = [f"{asset.key}:" for asset in assets.ASSETS.values() if asset.key != assets.DEFAULT]
    mine = assets.current().named("")
    runs = BacktestRun.objects.order_by("-created_at")
    if mine:
        runs = runs.filter(name__startswith=mine)
    else:
        for prefix in others:
            runs = runs.exclude(name__startswith=prefix)
    return runs.filter(name__startswith=assets.current().named(name_prefix)) if name_prefix else runs


def cost_by_agent():
    return list(
        AgentRun.objects.values("agent", "is_backtest")
        .annotate(calls=Count("id"), input_tokens=Sum("input_tokens"),
                  output_tokens=Sum("output_tokens"), cost_usd=Sum("cost_usd"))
        .filter(cost_usd__gt=0)
        .order_by("agent", "is_backtest")
    )


def cost_by_day():
    """Money spent per calendar day of the call (not the decision date) and agent."""
    return list(
        AgentRun.objects.filter(cost_usd__gt=0)
        .annotate(day=TruncDate("created_at"))
        .values("day", "agent")
        .annotate(cost_usd=Sum("cost_usd"), calls=Count("id"))
        .order_by("day", "agent")
    )


def paid_live_days():
    """How many decision days had a paid live call."""
    return AgentRun.objects.filter(cost_usd__gt=0, is_backtest=False).values("date").distinct().count()


def prompt_versions(agent=None):
    versions = PromptVersion.objects.order_by("agent", "-version")
    return versions.filter(agent=agent) if agent else versions


def runs_for_version(version):
    return AgentRun.objects.filter(prompt_version=version)


def opus_runs(start, end):
    """Every run of the configured model (AI_MODEL) in the period (live and backtest), oldest
    first. Runs of another model, made to compare, stay out."""
    return (AgentRun.objects.filter(date__range=(start, end), opus_score__isnull=False, model=settings.AI_MODEL,
                                    agent__in=domains.agents())
            .select_related("prompt_version").order_by("date", "created_at"))
