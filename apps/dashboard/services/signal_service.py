"""Every day's call from each domain's rule, ML and Opus agent and from the vote, judged
against what the price did.

A score s means "s% sure the price is higher after the horizon". s >= 55 is a Buy call
(s% sure it rises), s <= 45 a Sell call (100 - s% sure it falls), in between Hold, which is
never judged. A call is right when the price moved its way; its result is the move seen
from the call's side (a Sell that saw the price fall 3% won 3%). Rules and ML come from
score_store (stored, recomputed when the code changes); Opus from the saved runs. The
vote is the current combining rule.
"""

import datetime
from dataclasses import dataclass

from ai.scoring import BEARISH_AT, BULLISH_AT
from apps.agents.models import AgentName
from apps.backtest.calibration import forward_returns
from apps.backtest.decision_rule import call as vote_call, net_votes, voters, vote
from apps.backtest.repositories import price_repository
from apps.backtest.services import combining_service, score_store
from apps.dashboard.repositories import report_repository

HORIZONS = (1, 3, 7)
DEFAULT_HORIZON = 7
START = datetime.date(2019, 1, 1)
SOURCES = [("rules", "Rules"), ("ml", "ML"), ("opus", "Opus")]
# The periods each part was chosen on, so the pages can say which numbers are a fair test.
PERIODS = [
    ("2019-2024", datetime.date(2019, 1, 1), datetime.date(2024, 12, 31),
     "The vote was chosen here. New to the rules."),
    ("Jan 2025 - Sep 2026", datetime.date(2025, 1, 1), datetime.date(2026, 9, 30),
     "The rules were chosen here. New to the vote."),
    ("Oct 2026 on", datetime.date(2026, 10, 1), None, "New to everything: the only clean test."),
]


@dataclass
class Call:
    signal: str                  # "buy", "sell", "hold"; "none" when there is no score
    score: float | None = None
    outcome: str = "none"        # "right", "wrong", "pending" or "none" (hold / no score)
    confidence: int | None = None  # how sure of its side, in percent
    result_pct: float | None = None  # the move seen from the call's side: + won, - lost
    note: str = ""


@dataclass
class Column:
    key: str
    agent: str                   # agent name, or "vote"
    label: str
    source: str                  # "rules", "ml", "opus" or "vote"
    source_label: str


def columns():
    result = [Column(f"{agent.value}:{source}", agent.value, agent.label, source, label)
              for agent in AgentName for source, label in SOURCES]
    result.append(Column("vote", "vote", "Vote", "vote", "Vote"))
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


def score_call(score, forward_return, note=""):
    signal = signal_for(score)
    result = Call(signal, score, judge(signal, forward_return), note=note)
    if signal in ("buy", "sell"):
        result.confidence = round(score if signal == "buy" else 100 - score)
        if forward_return is not None:
            result.result_pct = forward_return * 100 * (1 if signal == "buy" else -1)
    return result


def vote_cell(votes, rule, forward_return):
    if not any(score is not None for score in votes.values()):
        return Call("none")
    signal = vote_call(votes, rule["min_net_votes"])
    buys = sum(1 for score in votes.values() if vote(score) == 1)
    sells = sum(1 for score in votes.values() if vote(score) == -1)
    result = Call(signal, outcome=judge(signal, forward_return),
                  note=f"{buys} Buy, {sells} Sell of {len(votes)} votes (net {net_votes(votes):+d})")
    if signal in ("buy", "sell") and forward_return is not None:
        result.result_pct = forward_return * 100 * (1 if signal == "buy" else -1)
    return result


def opus_history(start, end):
    """{date: {agent: run}}: the newest run with an Opus score per day and agent."""
    history = {}
    for run in report_repository.opus_runs(start, end):
        history.setdefault(run.date, {})[run.agent] = run
    return history


def day_calls(scores, opus_runs, rule, forward_return):
    """scores: {"rules": {agent: score}, "ml": {...}} for one day."""
    calls = {}
    opus_scores = {}
    for agent in AgentName.values:
        calls[f"{agent}:rules"] = score_call(scores["rules"].get(agent), forward_return)
        calls[f"{agent}:ml"] = score_call(scores["ml"].get(agent), forward_return)
        run = opus_runs.get(agent)
        opus_scores[agent] = run.opus_score if run else None
        note = f"prompt v{run.prompt_version.version}" if run and run.prompt_version else ""
        calls[f"{agent}:opus"] = score_call(opus_scores[agent], forward_return, note)
    by_source = {**scores, "opus": opus_scores}
    calls["vote"] = vote_cell(voters(by_source, rule["sources"]), rule, forward_return)
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


def build_rows(start, end, horizon):
    """One row per day (oldest first) with every column's call and the price move."""
    days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
    closes = price_repository.closes(start, end + datetime.timedelta(days=horizon))
    days = [day for day in days if day in closes]
    returns = forward_returns(days, closes, horizon)
    rules, ml = score_store.scores(days)
    opus = opus_history(start, end)
    rule = combining_service.current_rule()
    rows = []
    for day in days:
        forward_return = returns.get(day)
        scores = {"rules": rules.get(day, {}), "ml": ml.get(day, {})}
        rows.append({
            "date": day,
            "close": closes.get(day),
            "return_pct": forward_return * 100 if forward_return is not None else None,
            "calls": day_calls(scores, opus.get(day, {}), rule, forward_return),
        })
    return rows, rule


def month_bounds(month):
    first = month.replace(day=1)
    following = (first + datetime.timedelta(days=32)).replace(day=1)
    return first, following - datetime.timedelta(days=1)


def months(last):
    """Every month from START to the month of `last`, oldest first."""
    result, month = [], START
    while month <= last:
        result.append(month)
        month = (month + datetime.timedelta(days=32)).replace(day=1)
    return result


def month_table(month=None, horizon=DEFAULT_HORIZON):
    last = price_repository.latest_close_date()
    if last is None:
        return {"rows": [], "columns": columns(), "summary": {}, "months": []}
    all_months = months(last)
    month = month.replace(day=1) if month else all_months[-1]
    month = min(max(month, all_months[0]), all_months[-1])
    start, end = month_bounds(month)
    rows, rule = build_rows(start, min(end, last), horizon)
    keys = [column.key for column in columns()]
    index = all_months.index(month)
    return {
        "rows": list(reversed(rows)), "columns": columns(), "summary": summarize(rows, keys),
        "month": month, "months": all_months, "rule": rule, "rule_text": combining_service.describe(rule),
        "previous": all_months[index - 1] if index > 0 else None,
        "next": all_months[index + 1] if index + 1 < len(all_months) else None,
        "price_change_pct": month_change(rows),
        "base_rate": base_rate(horizon, last),
    }


def base_rate(horizon, last):
    """How often the price was higher after `horizon` days since START: the bar to beat."""
    closes = price_repository.closes(START, last)
    moves = [move for move in forward_returns(sorted(closes), closes, horizon).values() if move]
    return sum(move > 0 for move in moves) / len(moves) * 100 if moves else None


def month_change(rows):
    closes = [row["close"] for row in rows if row["close"]]
    return (closes[-1] / closes[0] - 1) * 100 if len(closes) > 1 else None


def overview(horizon=DEFAULT_HORIZON):
    """Hit rates per month and per period for every column, from START to the last price."""
    last = price_repository.latest_close_date()
    if last is None:
        return {"months": [], "periods": [], "columns": columns()}
    rows, rule = build_rows(START, last, horizon)
    keys = [column.key for column in columns()]
    by_month = {}
    for row in rows:
        by_month.setdefault(row["date"].replace(day=1), []).append(row)
    month_rows = [{"month": month, "summary": summarize(group, keys), "price_change_pct": month_change(group)}
                  for month, group in sorted(by_month.items(), reverse=True)]
    periods = []
    for name, start, end, note in PERIODS:
        group = [row for row in rows if start <= row["date"] and (end is None or row["date"] <= end)]
        if group:
            periods.append({"name": name, "note": note, "summary": summarize(group, keys), "days": len(group)})
    return {"months": month_rows, "periods": periods, "columns": columns(), "rule": rule,
            "rule_text": combining_service.describe(rule), "base_rate": base_rate(horizon, last)}
