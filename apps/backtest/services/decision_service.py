from apps.agents.models import AgentName, AgentRun
from apps.backtest.decision_rule import is_buy
from apps.backtest.models import Decision
from apps.backtest.services import combining_service

SCORE_FIELDS = {"rules": "rule_score", "ml": "ml_score", "opus": "opus_score"}


def latest_scores(date, score_type):
    """Each agent's live score for the date (the newest run if an agent ran twice)."""
    scores = {agent: None for agent in AgentName.values}
    runs = AgentRun.objects.filter(date=date, is_backtest=False).order_by("created_at")
    for run in runs:
        scores[run.agent] = getattr(run, SCORE_FIELDS[score_type])
    return scores


def make_decision(date):
    """Apply the chosen combining rule to the day's agent runs and save the Decision."""
    rule = combining_service.current_rule()
    scores = latest_scores(date, rule["score_type"])
    buy = is_buy(scores, rule["threshold"], rule["agents_required"])
    return Decision.objects.create(
        date=date,
        technical_score=scores["technical"],
        derivatives_score=scores["derivatives"],
        macro_score=scores["macro"],
        signal=Decision.Signal.BUY if buy else Decision.Signal.NO_TRADE,
        threshold=rule["threshold"],
        agents_required=rule["agents_required"],
    )
