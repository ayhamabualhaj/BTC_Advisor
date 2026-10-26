"""Runs a day's agents: builds each domain's Brief, runs the Flow, saves one AgentRun per domain."""

from ai import flow
from ai.brief import Brief
from ai.domains import DOMAINS
from apps.agents.models import AgentRun
from apps.agents.services import memory_service, prompt_service, rule_scoring_service
from apps.data.repositories.market_data_repository import series


def close_on(date):
    rows = series("binance", "close", date, 1)
    return rows[-1][1] if rows and rows[-1][0] == date else None


def stop_loss_price(close, stop_pct):
    if close is None or stop_pct is None:
        return None
    return round(close * (1 - stop_pct / 100), 2)


def make_brief(agent, date, cases=None, with_similar=False):
    """Everything one domain's agents may know on `date`, read from the database here
    because the Flow's steps cannot use it. `cases` (from memory_service.known_cases)
    saves reloading the memory for every day of a backtest."""
    snapshot = rule_scoring_service.snapshot(agent, date)
    setup = DOMAINS[agent].inputs.model_input(snapshot)
    brief = Brief(agent, date, snapshot, setup, training=memory_service.training_cases(agent, date, cases),
                  ml_features=DOMAINS[agent].ml.features(snapshot, setup))
    if with_similar:
        brief.similar = memory_service.as_model_input(memory_service.similar_cases(agent, date, setup))
    return brief


def run_agents(date, agents=None, use_opus=True, client=None, is_backtest=False):
    """Each domain's rule, ML and (if use_opus) Opus agent; they never see each other's results."""
    agents = agents or list(DOMAINS)
    prompts = {agent: prompt_service.current_version(agent, DOMAINS[agent].opus.PROMPT_FILE)
               for agent in agents} if use_opus else {}
    briefs = {}
    for agent in agents:
        briefs[agent] = make_brief(agent, date, with_similar=use_opus)
        if use_opus:
            briefs[agent].prompt_text = prompts[agent].prompt_text
    verdicts = flow.run(briefs, use_opus, client)
    return [save(briefs[verdict.agent], verdict, prompts.get(verdict.agent), is_backtest) for verdict in verdicts]


def save(brief, verdict, prompt, is_backtest):
    rules, ml, opus = verdict.rules, verdict.ml, verdict.opus
    answer = opus.data if opus and opus.data else {}
    key_data = {**brief.snapshot, "skipped": rules.skipped, "rule_reasons": rules.reasons, "ml_reasons": ml.reasons}
    if opus:
        key_data["model_input"] = brief.opus_input()
    return AgentRun.objects.create(
        date=brief.date,
        agent=brief.agent,
        rule_score=rules.score,
        ml_score=ml.score,
        opus_score=answer.get("opus_score"),
        # Without a valid Opus reply the run falls back to the rules' direction and reasons.
        direction=answer.get("direction", rules.direction),
        reasons=answer.get("reasons", rules.reasons),
        key_data=key_data,
        suggested_stop_loss=stop_loss_price(close_on(brief.date), answer.get("suggested_stop_loss_pct")),
        prompt_version=prompt,
        model=opus.model if opus else "",
        input_tokens=opus.input_tokens if opus else 0,
        output_tokens=opus.output_tokens if opus else 0,
        cost_usd=opus.cost_usd if opus else 0,
        is_backtest=is_backtest,
        error=opus.error if opus else "",
    )
