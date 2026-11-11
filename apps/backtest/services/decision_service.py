from ai import domains
from apps.agents.models import AgentRun
from apps.backtest.decision_rule import GROUPS, decide, overall_net
from apps.backtest.models import Decision
from apps.backtest.services import combining_service
from apps.data import assets

SCORE_FIELDS = {"rules": "rule_score", "ml": "ml_score", "opus": "opus_score"}


def latest_scores(date, score_type):
    """Each agent's live score for the date (the newest run if an agent ran twice)."""
    scores = {agent: None for agent in domains.agents()}
    runs = AgentRun.objects.filter(date=date, is_backtest=False, agent__in=domains.agents()).order_by("created_at")
    for run in runs:
        scores[run.agent] = getattr(run, SCORE_FIELDS[score_type])
    return scores


def make_decision(date):
    """Apply the chosen two-round vote to the day's agent runs and save the Decision."""
    rule = combining_service.current_rule()
    by_source = {source: latest_scores(date, source) for source in GROUPS}
    groups, signal = decide(by_source, rule)
    # The per-agent columns show the rule scores, by domain (an asset may lack one).
    asset = assets.current()
    shown = {asset.domain(agent): score for agent, score in by_source["rules"].items()}
    return Decision.objects.create(
        date=date,
        asset=asset.key,
        technical_score=shown.get("technical"),
        derivatives_score=shown.get("derivatives"),
        macro_score=shown.get("macro"),
        signal=Decision.Signal.BUY if signal == "buy" else Decision.Signal.NO_TRADE,
        rule=rule,
        group_calls=groups,
        net_votes=overall_net(groups),
    )
