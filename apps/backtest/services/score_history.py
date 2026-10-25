"""Daily agent scores over a period, for backtests: {date: {agent: score}}."""

from apps.agents.models import AgentRun
from apps.agents.services import rule_scoring_service


def rule_scores(days):
    """Rule scores computed fresh for each day from data known on that day."""
    history = {}
    for day in days:
        results = rule_scoring_service.run_rules(day)
        history[day] = {agent: rule_score.score for agent, (_, rule_score) in results.items()}
    return history


def opus_scores(days, prompt_versions):
    """Opus scores saved by the Opus backtest, for the given prompt version per agent."""
    history = {day: {agent: None for agent in prompt_versions} for day in days}
    runs = AgentRun.objects.filter(
        is_backtest=True, date__in=days, opus_score__isnull=False,
        prompt_version__in=prompt_versions.values(),
    ).order_by("created_at")
    for run in runs:
        # A later run of the same day and version replaces an earlier one.
        history[run.date][run.agent] = run.opus_score
    return history
