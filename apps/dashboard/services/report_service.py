"""Read-only summaries shared by the REST API and the web pages."""

import datetime

from ai.domains import has
from apps.agents.models import AgentName
from apps.backtest import calibration
from apps.backtest.decision_rule import (GROUPS, OVERALL_NEEDED, SOLO, STRONG_NEEDED, STRONG_NET, STRONG_ONLY, VOTERS,
                                          VOTERS_ROUND_2, strong_net)
from apps.backtest.repositories import price_repository
from apps.dashboard.repositories import report_repository
from apps.dashboard.services import signal_service

SCORE_FIELDS = {"rules": "rule_score", "ml": "ml_score", "opus": "opus_score"}
# The track record starts where the vote's own test period does (the LLM votes from here).
TRACK_RECORD_START = datetime.date(2025, 1, 1)
RECENT_TRADES = 10
# Fewer judged trades than this cannot tell a real edge from luck, and the page says so.
ENOUGH_TRADES = 30
# The Today page's price chart: this many days back.
PRICE_CHART_DAYS = 120
# One sentence per agent on what it looks at, for its page.
AGENT_NOTES = {
    "technical": "Reads Bitcoin's own price: trend against its 20, 50 and 200-day averages, momentum (RSI, MACD), "
                 "recent moves, support and resistance.",
    "derivatives": "Reads the futures market: funding rates, open interest, how many accounts are long, liquidations.",
    "macro": "Reads the wider economy: the dollar, the Nasdaq and S&P 500, the Fed, the 2-year yield, inflation, ETF flows.",
    "stress": "Reads fear in the stock and bond markets: VIX, MOVE and the Chicago Fed's financial conditions index. "
              "It has only an ML agent and votes on its own.",
    "riskon": "One rule: when Bitcoin and the Nasdaq both rose today, it says Sell for tomorrow; otherwise it holds. "
              "It never says Buy and votes on its own.",
    "dollar": "Reads the dollar index: its moves over a week, a month and three months, and how Bitcoin has moved "
              "against it. It has only an ML agent and votes only in the second strong signal (Strong + dollar), never in the overall vote.",
}


def today():
    """The latest decision and the agent runs behind it (or the latest runs if no decision yet)."""
    decision = report_repository.latest_decision()
    date = decision.date if decision else report_repository.latest_live_date()
    runs = report_repository.latest_live_runs(date) if date else []
    return {"date": date, "decision": decision, "agent_runs": runs}


def price_now():
    """The last Bitcoin close and its move over 1 and 7 days, for the Today page."""
    last = price_repository.latest_close_date()
    if last is None:
        return None
    closes = price_repository.closes(last - datetime.timedelta(days=7), last)

    def change(days):
        earlier = closes.get(last - datetime.timedelta(days=days))
        return (closes[last] / earlier - 1) * 100 if earlier else None

    return {"date": last, "close": closes[last], "change_1d_pct": change(1), "change_7d_pct": change(7)}


def trades(rows, key):
    """A column's Buy / Sell calls as trades, oldest first: days in a row with the same call are
    one trade, judged on its first day. `strong` and `strong_dollar` mark a trade that strong
    signal backed."""
    found, previous = [], None
    for row in rows:
        call = row["calls"][key]
        signal = call.signal if call.signal in ("buy", "sell") else None
        if signal and signal != previous:
            found.append({"date": row["date"], "signal": signal, "outcome": call.outcome,
                          "move_pct": row["return_pct"], "days": 0, "strong": False, "strong_dollar": False})
        if signal:
            found[-1]["days"] += 1
            for flag, column in (("strong", signal_service.STRONG), ("strong_dollar", signal_service.STRONG_DOLLAR)):
                found[-1][flag] = found[-1][flag] or row["calls"][column].signal == signal
        previous = signal
    return found


def record(rows, key):
    every = trades(rows, key)
    judged = [trade for trade in every if trade["outcome"] in ("right", "wrong")]
    right = sum(1 for trade in judged if trade["outcome"] == "right")
    return {"trades": len(judged), "right": right, "hit_rate": right / len(judged) * 100 if judged else None,
            "enough": len(judged) >= ENOUGH_TRADES, "recent": list(reversed(every))[:RECENT_TRADES]}


def price_chart(rows):
    """The last months of Bitcoin closes with the overall vote's Buy and Sell days marked on them."""
    recent = rows[-PRICE_CHART_DAYS:]

    def marked(signal):
        return [row["close"] if row["calls"]["vote"].signal == signal else None for row in recent]

    return {"labels": [row["date"].isoformat() for row in recent], "close": [row["close"] for row in recent],
            "buy": marked("buy"), "sell": marked("sell")}


def track_record():
    """How the overall vote's and the strong signal's past trades turned out after 7 days."""
    last = price_repository.latest_close_date()
    if last is None or last < TRACK_RECORD_START:
        return None
    rows, _ = signal_service.build_rows(TRACK_RECORD_START, last, signal_service.DEFAULT_HORIZON)
    return {"since": TRACK_RECORD_START, "needed": OVERALL_NEEDED, "strong_needed": STRONG_NEEDED, "strong_net": STRONG_NET,
            "vote": record(rows, "vote"), "strong": record(rows, signal_service.STRONG),
            "strong_dollar": record(rows, signal_service.STRONG_DOLLAR), "chart": price_chart(rows)}


def agent_kinds(agent):
    """[(kind, label)] of the kinds of agent a domain has: stress has only ML, the risk-on day only rules."""
    return [(kind, label) for kind, label in signal_service.sources() if has(agent, kind)]


def kind_scores(agent, run):
    """[(label, score)] of a run, for the kinds its domain has."""
    return [(label, getattr(run, SCORE_FIELDS[kind])) for kind, label in agent_kinds(agent)]


def agent_record(agent):
    """An agent's 7-day hit rate per period and kind of score: [(period, [(kind label, summary)])]."""
    data = signal_service.overview()
    columns = [column for column in data["columns"] if column.agent == agent]
    return [(period, [(column.source_label, period["summary"][column.key]) for column in columns])
            for period in data["periods"]]


def group_members(source):
    """[(agent, votes)] for a group vote: every agent of that kind, and whether it counts."""
    solo_agents = {agent for _, agent in {**SOLO, **STRONG_ONLY}.values()}
    allowed = VOTERS.get(source)
    return [(agent, allowed is None or agent in allowed) for agent in AgentName.values
            if has(agent, source) and agent not in solo_agents]


def vote_breakdown(decision):
    """Who voted what in a Decision's overall vote: the five voters, and each one's agents.

    A voter whose call is "none" did not vote (no score that day); an agent with
    `votes` False is scored and shown but does not count in its group.
    """
    runs = {run.agent: run for run in report_repository.latest_live_runs(decision.date)}
    labels = signal_service.voter_labels()
    voters = []
    for key in VOTERS_ROUND_2 + list(STRONG_ONLY):
        if key in GROUPS:
            source, members = key, group_members(key)
        else:
            source, agent = {**SOLO, **STRONG_ONLY}[key]
            members = [(agent, True)]
        rows = []
        for agent, votes in members:
            score = getattr(runs[agent], SCORE_FIELDS[source]) if agent in runs else None
            rows.append({"label": AgentName(agent).label, "score": score,
                         "call": signal_service.signal_for(score), "votes": votes})
        voters.append({"key": key, "label": labels[key], "call": decision.group_calls.get(key, "none"), "agents": rows,
                       "strong_only": key in STRONG_ONLY})
    # The counts are the overall vote's: the dollar agent is listed but votes only in the strong signal.
    calls = [voter["call"] for voter in voters if not voter["strong_only"]]
    return {"voters": voters, "needed": OVERALL_NEEDED, "buy": calls.count("buy"), "sell": calls.count("sell"),
            "hold": calls.count("hold"), "missing": calls.count("none"),
            "strong_net": strong_net(decision.group_calls), "strong_net_needed": STRONG_NET}


def costs():
    rows = report_repository.cost_by_agent()
    total = sum(row["cost_usd"] for row in rows)
    live = [row for row in rows if not row["is_backtest"]]
    live_usd = sum(row["cost_usd"] for row in live)
    live_days = report_repository.paid_live_days()
    return {"total_usd": total, "live_usd": live_usd, "backtest_usd": total - live_usd,
            "calls": sum(row["calls"] for row in rows), "live_days": live_days,
            "per_live_day_usd": live_usd / live_days if live_days else None,
            "by_agent": rows, "by_day": report_repository.cost_by_day()}


def hit_rate_7d(runs):
    """Percent of a version's directional Opus calls that were right after 7 days."""
    scored = [run for run in runs if run.opus_score is not None and run.opus_score != 50]
    if not scored:
        return None, 0
    days = sorted({run.date for run in scored})
    closes = price_repository.closes(days[0], days[-1] + datetime.timedelta(days=calibration.HORIZON_DAYS))
    returns = calibration.forward_returns(days, closes)
    judged = [(run.opus_score > 50) == (returns[run.date] > 0) for run in scored
              if run.date in returns and returns[run.date] != 0]
    if not judged:
        return None, 0
    return sum(judged) / len(judged) * 100, len(judged)


def prompt_history(agent=None):
    history = []
    for version in report_repository.prompt_versions(agent):
        runs = list(report_repository.runs_for_version(version))
        hit_rate, judged = hit_rate_7d(runs)
        opus_scores = [run.opus_score for run in runs if run.opus_score is not None]
        history.append({
            "version": version,
            "runs": len(runs),
            "backtest_runs": sum(1 for run in runs if run.is_backtest),
            "errors": sum(1 for run in runs if run.error),
            "cost_usd": sum(run.cost_usd for run in runs),
            "avg_opus_score": sum(opus_scores) / len(opus_scores) if opus_scores else None,
            "hit_rate_7d": hit_rate,
            "judged_calls": judged,
        })
    return history


def agent_history(agent, is_backtest=False, limit=180):
    """Oldest-first runs of one agent, one per day, for its score chart and table.

    A day run twice (rules only, then with the LLM) shows once: the run with an LLM score if
    there is one, else the newest.
    """
    by_day = {}
    for run in report_repository.agent_runs(agent, is_backtest)[:limit]:  # newest first
        kept = by_day.get(run.date)
        if kept is None or (kept.opus_score is None and run.opus_score is not None):
            by_day[run.date] = run
    return [by_day[day] for day in sorted(by_day)]


def backtest_overview():
    """The newest BacktestRun of every name, grouped for the backtest page."""
    latest = {}
    for run in report_repository.backtest_runs():
        latest.setdefault(run.name, run)
    groups = {"strategies": [], "calibration": [], "combining": []}
    for name, run in sorted(latest.items()):
        if name.endswith(":calibration"):
            groups["calibration"].append(run)
        elif name == "combining_rule":
            groups["combining"].append(run)
        else:
            groups["strategies"].append(run)
    return groups
