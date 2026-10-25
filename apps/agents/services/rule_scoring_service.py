from apps.agents.derivatives import rules as derivatives_rules
from apps.agents.macro import rules as macro_rules
from apps.agents.models import AgentName, AgentRun
from apps.agents.technical import rules as technical_rules
from apps.data.services import indicator_service

AGENTS = {
    AgentName.TECHNICAL: (indicator_service.technical_snapshot, technical_rules.score),
    AgentName.DERIVATIVES: (indicator_service.derivatives_snapshot, derivatives_rules.score),
    AgentName.MACRO: (indicator_service.macro_snapshot, macro_rules.score),
}


def score_agent(agent, date):
    """Rule score for one agent on one date, with the snapshot it was based on."""
    build_snapshot, score = AGENTS[agent]
    snapshot = build_snapshot(date)
    return snapshot, score(snapshot)


def run_rules(date, save=False, is_backtest=False):
    """Score every agent for a date. With save=True each result is stored as a rule-only AgentRun."""
    results = {}
    for agent in AGENTS:
        snapshot, rule_score = score_agent(agent, date)
        results[agent] = (snapshot, rule_score)
        if save:
            AgentRun.objects.create(
                date=date,
                agent=agent,
                rule_score=rule_score.score,
                direction=rule_score.direction,
                reasons=rule_score.reasons,
                key_data={**snapshot, "skipped": rule_score.skipped, "rule_reasons": rule_score.reasons},
                is_backtest=is_backtest,
            )
    return results
