"""Two prompt versions, each with the input it was written for, asked the same days by the
same model, then judged the same way. Paid: one call per version, agent and day."""

import datetime
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal

from ai import inputs_v2, opus_client
from ai.domains import DOMAINS, with_kind
from apps.agents.models import AgentRun, PromptVersion
from apps.agents.services import memory_service, prompt_service, rule_scoring_service
from apps.backtest.calibration import forward_returns
from apps.backtest.repositories import price_repository
from apps.backtest.services.model_comparison_service import Tally

WORKERS = 8  # parallel API calls; the SDK retries 429s
V2_SIMILAR_CASES = 5
# About 2,400 input and 400 output tokens per call, for estimates before real costs exist.
TOKENS_PER_CALL = (2400, 400)


@dataclass
class Progress:
    calls: int = 0
    spent_usd: Decimal = Decimal("0")
    errors: list = field(default_factory=list)
    stopped_at_cap: bool = False


def versions(old, new):
    """{"old"/"new": {agent: PromptVersion}}. The new one is the prompt files on disk."""
    found = {"old": {}, "new": {}}
    for agent in with_kind("opus"):
        found["old"][agent] = PromptVersion.objects.get(agent=agent, version=old)
        current = prompt_service.current_version(agent, DOMAINS[agent].opus.PROMPT_FILE)
        if current.version != new:
            raise ValueError(f"{agent}: the prompt files are v{current.version}, not v{new}")
        found["new"][agent] = current
    return found


def v2_input(agent, date, snapshot):
    """Prompt v2's input: its own fields and the 5 closest past setups, as it saw them."""
    setup = inputs_v2.MODEL_INPUTS[agent](snapshot)
    cases = memory_service.similar_cases(agent, date, setup, limit=V2_SIMILAR_CASES)
    similar = [{"setup": {k: v for k, v in json.loads(case.setup_summary).items() if k in setup},
                "return_after_7d_pct": case.return_7d_pct} for case in cases]
    return {**setup, "similar_past_setups": similar}


def v3_input(agent, date, snapshot):
    setup = DOMAINS[agent].inputs.model_input(snapshot)
    return {**setup, "similar_past_days": memory_service.similar_summary(agent, date, setup)}


INPUTS = {"old": v2_input, "new": v3_input}


def done(model, version):
    return set(AgentRun.objects.filter(model=model, prompt_version=version, is_backtest=True,
                                       opus_score__isnull=False).values_list("date", flat=True))


def pending(model, found, days):
    """[(side, agent, day)] still to ask, oldest day first."""
    work = []
    for side in ("old", "new"):
        for agent, version in found[side].items():
            finished = done(model, version)
            work += [(side, agent, day) for day in days if day not in finished]
    return sorted(work, key=lambda item: (item[2], item[1], item[0]))


def per_call(model):
    return opus_client.cost_usd(*TOKENS_PER_CALL, model)


def run(model, found, days, max_cost_usd, client=None, on_run=None):
    """Asks in parallel batches; stops before a batch that could pass the cap."""
    client = client or opus_client.make_client()
    progress = Progress()
    work = pending(model, found, days)
    estimate = per_call(model)
    with ThreadPoolExecutor(WORKERS) as pool:
        for start in range(0, len(work), WORKERS):
            batch = work[start:start + WORKERS]
            if progress.spent_usd + estimate * len(batch) > max_cost_usd:
                progress.stopped_at_cap = True
                break
            # Inputs are built here, on this thread: the database is not shared with the workers.
            asks = []
            for side, agent, day in batch:
                snapshot, rules = rule_scoring_service.score_agent(agent, day)
                asks.append((side, agent, day, INPUTS[side](agent, day, snapshot), rules.score))
            replies = pool.map(lambda a: opus_client.ask(found[a[0]][a[1]].prompt_text, a[3], client=client, model=model), asks)
            for (side, agent, day, model_input, rule_score), reply in zip(asks, replies):
                answer = reply.data or {}
                run_ = AgentRun.objects.create(
                    date=day, agent=agent, rule_score=rule_score, opus_score=answer.get("opus_score"),
                    direction=answer.get("direction", ""), reasons=answer.get("reasons", []),
                    key_data={"model_input": model_input, "prompt_comparison": True},
                    prompt_version=found[side][agent], model=model, input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens, cost_usd=reply.cost_usd, is_backtest=True, error=reply.error)
                progress.calls += 1
                progress.spent_usd += reply.cost_usd
                if reply.error:
                    progress.errors.append(f"{day} {agent} v{found[side][agent].version}: {reply.error}")
                if on_run:
                    on_run(run_)
            # Keep the estimate honest as real costs come in.
            estimate = max(progress.spent_usd / progress.calls, Decimal("0.0001"))
    return progress


def compare(model, found, days, horizon=7):
    """{period: {agent or "all": {"old": Tally, "new": Tally}}} over days both versions answered."""
    scores = {}
    for side in ("old", "new"):
        for agent, version in found[side].items():
            runs = AgentRun.objects.filter(model=model, prompt_version=version, is_backtest=True,
                                           opus_score__isnull=False, date__in=days).order_by("created_at")
            for run_ in runs:
                scores.setdefault((run_.date, agent), {})[side] = (run_.opus_score, run_.cost_usd)
    if not scores:
        return {}
    closes = price_repository.closes(days[0], days[-1] + datetime.timedelta(days=horizon))
    moves = forward_returns(days, closes, horizon)
    result = {}
    for (day, agent), both in sorted(scores.items()):
        if len(both) < 2:
            continue
        for period in (str(day.year), "all"):
            for key in (agent, "all"):
                row = result.setdefault(period, {}).setdefault(key, {"old": Tally(), "new": Tally()})
                for side in ("old", "new"):
                    row[side].add(both[side][0], moves.get(day), both[side][1])
    return result


def score_spread(model, version, days):
    """How the version's scores spread: share of days below 45, 46-54 and 55 or more."""
    values = list(AgentRun.objects.filter(model=model, prompt_version=version, is_backtest=True,
                                          opus_score__isnull=False, date__in=days).values_list("opus_score", flat=True))
    if not values:
        return None
    return {"sell": sum(v <= 45 for v in values) / len(values) * 100,
            "hold": sum(45 < v < 55 for v in values) / len(values) * 100,
            "buy": sum(v >= 55 for v in values) / len(values) * 100, "days": len(values)}
