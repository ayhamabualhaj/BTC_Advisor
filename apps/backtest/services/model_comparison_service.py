"""Asks another Claude model exactly what the configured model (AI_MODEL, Opus) was asked
in its backtest: the same saved prompt version and the same saved model input, day by day.
So the two are compared on identical questions, and nothing is rebuilt from today's code.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings

from ai import opus_client
from apps.agents.models import AgentName, AgentRun
from apps.backtest.calibration import forward_returns
from apps.backtest.repositories import price_repository

HORIZONS = (1, 3, 7)


@dataclass
class ReplayProgress:
    calls: int = 0
    spent_usd: Decimal = Decimal("0")
    errors: list = field(default_factory=list)
    stopped_at_cap: bool = False


def reference_runs():
    """The configured model's backtest runs that kept their exact input, oldest first."""
    runs = (AgentRun.objects.filter(is_backtest=True, model=settings.AI_MODEL, opus_score__isnull=False,
                                    prompt_version__isnull=False)
            .select_related("prompt_version").order_by("date", "agent", "created_at"))
    # The newest run per day, agent and prompt version, like the backtest itself.
    latest = {(run.date, run.agent, run.prompt_version_id): run for run in runs if "model_input" in run.key_data}
    return list(latest.values())


def done_keys(model):
    return set(AgentRun.objects.filter(is_backtest=True, model=model, opus_score__isnull=False)
               .values_list("date", "agent", "prompt_version_id"))


def pending(model):
    done = done_keys(model)
    return [run for run in reference_runs() if (run.date, run.agent, run.prompt_version_id) not in done]


def estimated_cost(run, model):
    # The reference run's tokens at the other model's prices, plus half for a longer answer.
    return opus_client.cost_usd(run.input_tokens, run.output_tokens, model) * Decimal("1.5")


def estimate(model):
    runs = pending(model)
    return len(runs), sum((estimated_cost(run, model) for run in runs), Decimal("0"))


def replay(model, max_cost_usd, client=None, on_run=None):
    """One call per pending reference run; stops before a call that could pass the cap."""
    progress = ReplayProgress()
    for reference in pending(model):
        if progress.spent_usd + estimated_cost(reference, model) > max_cost_usd:
            progress.stopped_at_cap = True
            break
        reply = opus_client.ask(reference.prompt_version.prompt_text, reference.key_data["model_input"],
                                client=client, model=model)
        answer = reply.data or {}
        run = AgentRun.objects.create(
            date=reference.date, agent=reference.agent, rule_score=reference.rule_score,
            ml_score=reference.ml_score, opus_score=answer.get("opus_score"),
            direction=answer.get("direction", ""), reasons=answer.get("reasons", []),
            key_data={"model_input": reference.key_data["model_input"], "replay_of": reference.id},
            prompt_version=reference.prompt_version, model=model,
            input_tokens=reply.input_tokens, output_tokens=reply.output_tokens, cost_usd=reply.cost_usd,
            is_backtest=True, error=reply.error,
        )
        progress.calls += 1
        progress.spent_usd += reply.cost_usd
        if reply.error:
            progress.errors.append(f"{run.date} {run.agent}: {reply.error}")
        if on_run:
            on_run(reference, run)
    return progress


@dataclass
class Tally:
    days: int = 0
    calls: int = 0
    right: int = 0
    brier_sum: float = 0.0
    brier_days: int = 0
    cost_usd: Decimal = Decimal("0")

    @property
    def hit_rate(self):
        return self.right / self.calls * 100 if self.calls else None

    @property
    def wrong_calls(self):
        return self.calls - self.right

    @property
    def brier(self):
        return self.brier_sum / self.brier_days if self.brier_days else None

    def add(self, score, move, cost):
        self.days += 1
        self.cost_usd += cost
        if move:  # judged only once the price moved
            went_up = move > 0
            self.brier_sum += (score / 100 - went_up) ** 2
            self.brier_days += 1
            if score >= 55 or score <= 45:
                self.calls += 1
                self.right += (score >= 55) == went_up


def compared_models():
    """Models with answers to compare against AI_MODEL, e.g. ["claude-haiku-5-5"]."""
    return sorted(set(AgentRun.objects.filter(is_backtest=True, opus_score__isnull=False)
                      .exclude(model__in=["", settings.AI_MODEL]).values_list("model", flat=True)))


def pairs(model):
    """[(reference run, other model's run)] for every question both answered, oldest first."""
    others = {(run.date, run.agent, run.prompt_version_id): run
              for run in AgentRun.objects.filter(is_backtest=True, model=model, opus_score__isnull=False)}
    return [(ref, others[key]) for ref in reference_runs()
            if (key := (ref.date, ref.agent, ref.prompt_version_id)) in others]


def moves(found, horizon):
    """{date: price change after `horizon` days} for the compared days (missing while waiting)."""
    if not found:
        return {}
    days = sorted({ref.date for ref, _ in found})
    closes = price_repository.closes(days[0], days[-1] + datetime.timedelta(days=horizon))
    return forward_returns(days, closes, horizon)


def compare(model, horizon=7, found=None):
    """{agent or "all": {"reference": Tally, "other": Tally, "same_side": n, "gap": mean |diff|}}
    over the days both models answered."""
    found = pairs(model) if found is None else found
    if not found:
        return {}
    moves_by_day = moves(found, horizon)
    result = {}
    for ref, other in found:
        for key in (ref.agent, "all"):
            row = result.setdefault(key, {"reference": Tally(), "other": Tally(), "same_side": 0, "gap_sum": 0.0})
            row["reference"].add(ref.opus_score, moves_by_day.get(ref.date), ref.cost_usd)
            row["other"].add(other.opus_score, moves_by_day.get(ref.date), other.cost_usd)
            row["same_side"] += side(ref.opus_score) == side(other.opus_score)
            row["gap_sum"] += abs(ref.opus_score - other.opus_score)
    for row in result.values():
        row["gap"] = row["gap_sum"] / row["reference"].days
    order = AgentName.values + ["all"]
    return {key: result[key] for key in order if key in result}


def side(score):
    return "buy" if score >= 55 else "sell" if score <= 45 else "hold"
