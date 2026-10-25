"""Runs one agent for one date: rule score in code, judgment score from Opus, one AgentRun."""

from apps.agents.ai import opus_client, prompts
from apps.agents.models import AgentRun
from apps.agents.services import rule_scoring_service
from apps.data.repositories.market_data_repository import series


def close_on(date):
    rows = series("binance", "close", date, 1)
    return rows[-1][1] if rows and rows[-1][0] == date else None


def stop_loss_price(close, stop_pct):
    if close is None or stop_pct is None:
        return None
    return round(close * (1 - stop_pct / 100), 2)


def run_agent(agent, prompt_file, model_input, date, client=None, is_backtest=False):
    snapshot, rule_score = rule_scoring_service.score_agent(agent, date)
    prompt = prompts.current_version(agent, prompt_file)
    data_for_opus = model_input(snapshot)
    reply = opus_client.ask(prompt.prompt_text, data_for_opus, client)
    verdict = reply.data or {}
    return AgentRun.objects.create(
        date=date,
        agent=agent,
        rule_score=rule_score.score,
        opus_score=verdict.get("opus_score"),
        # Without a valid Opus reply the run falls back to the rules' direction and reasons.
        direction=verdict.get("direction", rule_score.direction),
        reasons=verdict.get("reasons", rule_score.reasons),
        key_data={
            **snapshot,
            "skipped": rule_score.skipped,
            "rule_reasons": rule_score.reasons,
            "model_input": data_for_opus,
        },
        suggested_stop_loss=stop_loss_price(close_on(date), verdict.get("suggested_stop_loss_pct")),
        prompt_version=prompt,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        cost_usd=reply.cost_usd,
        is_backtest=is_backtest,
        error=reply.error,
    )
