from apps.agents.models import AgentName, AgentRun
from apps.backtest.decision_rule import call, net_votes, voters
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
    """Apply the chosen vote to the day's agent runs and save the Decision."""
    rule = combining_service.current_rule()
    by_source = {source: latest_scores(date, source) for source in rule["sources"]}
    votes = voters(by_source, rule["sources"])
    # The first voting source fills the per-agent columns (rules unless the vote changes).
    shown = by_source[rule["sources"][0]]
    return Decision.objects.create(
        date=date,
        technical_score=shown["technical"],
        derivatives_score=shown["derivatives"],
        macro_score=shown["macro"],
        signal=Decision.Signal.BUY if call(votes, rule["min_net_votes"]) == "buy" else Decision.Signal.NO_TRADE,
        rule=rule,
        net_votes=net_votes(votes),
    )
