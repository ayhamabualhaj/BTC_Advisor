from apps.agents.models import AgentName, AgentRun
from apps.backtest.decision_rule import GROUPS, decide, overall_net
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
    """Apply the chosen two-round vote to the day's agent runs and save the Decision."""
    rule = combining_service.current_rule()
    by_source = {source: latest_scores(date, source) for source in GROUPS}
    groups, signal = decide(by_source, rule)
    # The per-agent columns show the rule scores.
    shown = by_source["rules"]
    return Decision.objects.create(
        date=date,
        technical_score=shown["technical"],
        derivatives_score=shown["derivatives"],
        macro_score=shown["macro"],
        signal=Decision.Signal.BUY if signal == "buy" else Decision.Signal.NO_TRADE,
        rule=rule,
        group_calls=groups,
        net_votes=overall_net(groups),
    )
