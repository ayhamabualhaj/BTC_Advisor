from ai.domains import DOMAINS, has, with_kind
from apps.agents.models import AgentName, AgentRun
from apps.data.services import indicator_service

SNAPSHOTS = {
    AgentName.TECHNICAL: indicator_service.technical_snapshot,
    AgentName.DERIVATIVES: indicator_service.derivatives_snapshot,
    AgentName.MACRO: indicator_service.macro_snapshot,
    AgentName.STRESS: indicator_service.stress_snapshot,
}


def snapshot(agent, date):
    """The indicator values one domain looks at, from data known on `date`."""
    return SNAPSHOTS[agent](date)


def score_agent(agent, date):
    """Rule score for one agent on one date (None without a rules agent), with its snapshot."""
    values = snapshot(agent, date)
    return values, DOMAINS[agent].rules.score(values) if has(agent, "rules") else None


def run_rules(date, save=False, is_backtest=False):
    """Score every agent for a date. With save=True each result is stored as a rule-only AgentRun."""
    results = {}
    for agent in with_kind("rules", list(SNAPSHOTS)):
        values, rule_score = score_agent(agent, date)
        results[agent] = (values, rule_score)
        if save:
            AgentRun.objects.create(
                date=date,
                agent=agent,
                rule_score=rule_score.score,
                direction=rule_score.direction,
                reasons=rule_score.reasons,
                key_data={**values, "skipped": rule_score.skipped, "rule_reasons": rule_score.reasons},
                is_backtest=is_backtest,
            )
    return results
