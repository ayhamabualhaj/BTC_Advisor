"""Daily agent scores over a period, for backtests: {date: {agent: score}}."""

from django.conf import settings

from ai.domains import DOMAINS
from apps.agents.models import AgentName, AgentRun
from apps.agents.services import agent_service, memory_service, rule_scoring_service
from apps.backtest.services import opus_backtest_service


def rule_scores(days):
    """Rule scores computed fresh for each day from data known on that day."""
    history = {}
    for day in days:
        results = rule_scoring_service.run_rules(day)
        history[day] = {agent: rule_score.score for agent, (_, rule_score) in results.items()}
    return history


def rule_and_ml_scores(days, on_progress=None):
    """Both free scores in one pass, so each day's snapshot is built once.

    The ML agent is retrained for every day on the cases known by then (walk-forward);
    the memory is read once per agent and cut by date in memory_service.training_cases.
    """
    cases = {agent: memory_service.known_cases(agent) for agent in DOMAINS}
    rules, ml = {}, {}
    for day in days:
        rules[day], ml[day] = {}, {}
        for agent, domain in DOMAINS.items():
            brief = agent_service.make_brief(agent, day, cases[agent])
            rules[day][agent] = domain.rules.score(brief.snapshot).score
            ml[day][agent] = domain.ml.score(brief).score
        if on_progress:
            on_progress(day)
    return rules, ml


def ml_scores(days):
    from apps.backtest.services import score_store  # stored scores; imported late (it imports this module)

    return score_store.scores(days)[1]


def opus_scores(days, prompt_versions):
    """Opus scores saved by the Opus backtest, for the given prompt version per agent."""
    history = {day: {agent: None for agent in prompt_versions} for day in days}
    runs = AgentRun.objects.filter(
        is_backtest=True, date__in=days, opus_score__isnull=False, model=settings.AI_MODEL,
        prompt_version__in=prompt_versions.values(),
    ).order_by("created_at")
    for run in runs:
        # A later run of the same day and version replaces an earlier one.
        history[run.date][run.agent] = run.opus_score
    return history


def scores(score_type, days):
    """Any kind of score by name. Opus only reads saved backtest runs, it never calls the API."""
    if score_type == "rules":
        from apps.backtest.services import score_store

        return score_store.scores(days)[0]
    if score_type == "ml":
        return ml_scores(days)
    return opus_scores(days, opus_backtest_service.prompt_versions(AgentName.values))
