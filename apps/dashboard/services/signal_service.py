"""Every day's call from each agent's rules and Opus, judged against what the price did.

A score of 55 or more is a Buy call and 45 or less a Sell call (the same cut-offs as the
rule directions); in between is Hold, which is never judged. A Buy is right when the price
is higher after the horizon, a Sell when it is lower. The combined column is the current
combining rule, which only ever says Buy.
"""

import datetime
from dataclasses import dataclass

from apps.agents.models import AgentName
from apps.agents.scoring import BEARISH_AT, BULLISH_AT
from apps.backtest.calibration import forward_returns
from apps.backtest.decision_rule import is_buy
from apps.backtest.repositories import price_repository
from apps.backtest.services import combining_service, score_history
from apps.dashboard.repositories import report_repository

HORIZONS = (1, 3, 7)
DEFAULT_HORIZON = 7
TEST_START = datetime.date(2026, 7, 1)


@dataclass
class Call:
    signal: str          # "buy", "sell" or "hold"; "none" when there is no score
    score: float | None = None
    outcome: str = "none"  # "right", "wrong", "pending" or "none" (hold / no score)
    note: str = ""       # extra detail for the tooltip, e.g. the prompt version


@dataclass
class Column:
    key: str
    agent: str           # agent name for the color dot, or "combined"
    label: str
    source: str          # "Rules" or "Opus"


def columns():
    result = []
    for agent in AgentName:
        result.append(Column(f"{agent.value}:rules", agent.value, agent.label, "Rules"))
        result.append(Column(f"{agent.value}:opus", agent.value, agent.label, "Opus"))
    result.append(Column("combined:rules", "combined", "Combined", "Rules"))
    result.append(Column("combined:opus", "combined", "Combined", "Opus"))
    return result


def signal_for(score):
    if score is None:
        return "none"
    if score >= BULLISH_AT:
        return "buy"
    if score <= BEARISH_AT:
        return "sell"
    return "hold"


def judge(signal, forward_return):
    if signal not in ("buy", "sell"):
        return "none"
    if forward_return is None:
        return "pending"
    if forward_return == 0:
        return "none"
    return "right" if (signal == "buy") == (forward_return > 0) else "wrong"


def opus_history(start, end):
    """{date: {agent: run}}: the newest run with an Opus score per day and agent."""
    history = {}
    for run in report_repository.opus_runs(start, end):
        history.setdefault(run.date, {})[run.agent] = run
    return history


def combined_call(scores, rule, forward_return):
    """The combining rule on one day's scores; it needs every agent's score to say anything."""
    if any(score is None for score in scores.values()):
        return Call("none")
    signal = "buy" if is_buy(scores, rule["threshold"], rule["agents_required"]) else "hold"
    return Call(signal, outcome=judge(signal, forward_return))


def day_calls(day, rule_scores, opus_runs, rule, forward_return):
    calls = {}
    opus_scores = {}
    for agent in AgentName.values:
        score = rule_scores.get(agent)
        calls[f"{agent}:rules"] = Call(signal_for(score), score, judge(signal_for(score), forward_return))
        run = opus_runs.get(agent)
        opus_scores[agent] = run.opus_score if run else None
        if run:
            signal = signal_for(run.opus_score)
            note = f"prompt v{run.prompt_version.version}" if run.prompt_version else ""
            calls[f"{agent}:opus"] = Call(signal, run.opus_score, judge(signal, forward_return), note)
        else:
            calls[f"{agent}:opus"] = Call("none")
    calls["combined:rules"] = combined_call(rule_scores, rule, forward_return)
    calls["combined:opus"] = combined_call(opus_scores, rule, forward_return)
    return calls


def summarize(rows, keys):
    """Per column: how many Buy/Sell calls were right, wrong and still waiting."""
    summary = {}
    for key in keys:
        outcomes = [row["calls"][key].outcome for row in rows]
        right, wrong = outcomes.count("right"), outcomes.count("wrong")
        summary[key] = {
            "right": right, "wrong": wrong, "pending": outcomes.count("pending"),
            "hit_rate": right / (right + wrong) * 100 if right + wrong else None,
        }
    return summary


def signal_table(start=None, end=None, horizon=DEFAULT_HORIZON, opus_days_only=False):
    """Rows newest first, one per day, with every column's call and the price move."""
    last = price_repository.latest_close_date()
    if last is None:
        return {"rows": [], "columns": columns(), "summary": {}, "start": start, "end": end}
    end = min(end or last, last)
    start = start or TEST_START
    days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
    opus = opus_history(start, end)
    if opus_days_only:
        days = [day for day in days if day in opus]

    closes = price_repository.closes(start, end + datetime.timedelta(days=horizon))
    returns = forward_returns(days, closes, horizon)
    rules = score_history.rule_scores(days)
    rule = combining_service.current_rule()

    rows = []
    for day in reversed(days):
        forward_return = returns.get(day)
        rows.append({
            "date": day,
            "close": closes.get(day),
            "return_pct": forward_return * 100 if forward_return is not None else None,
            "calls": day_calls(day, rules[day], opus.get(day, {}), rule, forward_return),
        })
    keys = [column.key for column in columns()]
    return {"rows": rows, "columns": columns(), "summary": summarize(rows, keys),
            "start": start, "end": end, "rule": rule}
