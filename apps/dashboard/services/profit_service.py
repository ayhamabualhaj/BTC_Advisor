"""The Profit page: what following each agent's calls would have earned.

Every column of the Signals page (9 agents, the Rules / ML / LLM votes and the overall
vote) becomes a strategy. A Buy (score >= 55, or the vote's Buy) at the close of day D holds
to the close of D + 1; with `short`, a Sell does the opposite; anything else stays out.
Compared with buying and holding over the same days. All math is apps/backtest/metrics.py.
"""

import datetime

from apps.agents.models import AgentName
from apps.backtest import metrics
from apps.backtest.decision_rule import decide
from apps.backtest.repositories import price_repository
from apps.backtest.services import backtest_service, combining_service, score_store
from apps.dashboard.services import signal_service

# (key, label, start, end); None = from the start / up to the last price. "90d" is relative.
PRESETS = [
    ("since-2025", "2025 to now", datetime.date(2025, 1, 1), None),
    ("2026", "2026", datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)),
    ("2025", "2025", datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)),
    ("90d", "Last 90 days", None, None),
    ("2019-2024", "2019 - 2024", datetime.date(2019, 1, 1), datetime.date(2024, 12, 31)),
    ("all", "All since 2019", signal_service.START, None),
]
DEFAULT_PRESET = "since-2025"
# The chart keeps at most about this many points per line (weekly beyond it), so years load fast.
MAX_CHART_POINTS = 400


def period(preset, start, end, last):
    """(preset key, start, end) clamped to the data; custom dates win over the preset."""
    if start or end:
        start = max(start or signal_service.START, signal_service.START)
        end = min(end or last, last)
        return "custom", start, max(start, end)
    key = preset if preset in dict((p[0], p) for p in PRESETS) else DEFAULT_PRESET
    if key == "90d":
        return key, last - datetime.timedelta(days=89), last
    _, _, preset_start, preset_end = next(p for p in PRESETS if p[0] == key)
    return key, preset_start, min(preset_end or last, last)


def daily_signals(days):
    """{column key: [signal per day]} for every Signals column; "none" when it had no score."""
    rules, ml = score_store.scores(days)
    llm = signal_service.opus_history(days[0], days[-1]) if days else {}
    rule = combining_service.current_rule()
    columns = signal_service.columns()
    signals = {column.key: [] for column in columns}
    for day in days:
        llm_runs = llm.get(day, {})
        by_source = {"rules": rules.get(day, {}), "ml": ml.get(day, {}),
                     "opus": {agent: run.opus_score for agent, run in llm_runs.items()}}
        for agent in AgentName.values:
            for source in ("rules", "ml", "opus"):
                signals[f"{agent}:{source}"].append(signal_service.signal_for(by_source[source].get(agent)))
        groups, overall = decide(by_source, rule)
        for source, signal in groups.items():
            signals[f"vote:{source}"].append(signal)
        signals["vote"].append(overall)
    return signals


def positions(signals, short):
    side = {"buy": 1, "sell": -1 if short else 0}
    return [side.get(signal, 0) for signal in signals]


def curve_points(days, curve):
    """Dates and profit in percent for the chart, thinned to about MAX_CHART_POINTS."""
    step = max(1, len(days) // MAX_CHART_POINTS)
    picked = list(range(0, len(days), step))
    if picked and picked[-1] != len(days) - 1:
        picked.append(len(days) - 1)
    return [days[i].isoformat() for i in picked], [round((curve[i] - 1) * 100, 2) for i in picked]


def row(column, signals, market, hold, short):
    scored = sum(1 for signal in signals if signal != "none")
    held = positions(signals, short)
    performance = metrics.performance(held, market.next_day_returns)
    curve = metrics.equity_curve(held, market.next_day_returns)
    return {
        "key": column.key, "agent": column.agent, "label": column.label, "source": column.source,
        "source_label": column.source_label, "name": f"{column.label} · {column.source_label}"
        if column.agent != "vote" else ("Overall vote" if column.source == "vote" else f"{column.source_label} vote"),
        "profit_pct": performance.total_profit_pct,
        "vs_hold_pct": performance.total_profit_pct - hold.total_profit_pct,
        "drawdown_pct": performance.max_drawdown_pct,
        "trades": performance.trade_count,
        "win_rate": performance.win_rate,
        "days_long": sum(1 for p in held if p > 0),
        "days_short": sum(1 for p in held if p < 0),
        "coverage_pct": scored / len(signals) * 100 if signals else 0,
        "curve": curve_points(market.days, curve)[1],
    }


def profit_page(preset=None, start=None, end=None, short=False):
    last = price_repository.latest_close_date()
    page = {"presets": [(key, label) for key, label, _, _ in PRESETS], "short": short, "rows": []}
    if last is None:
        return page
    # The last day has no next-day price yet, so it cannot be scored.
    key, start, end = period(preset, start, end, last - datetime.timedelta(days=1))
    market = backtest_service.load_market(start, end)
    page.update({"preset": key, "start": start, "end": end, "days": len(market.days)})
    if not market.days:
        return page
    hold = metrics.performance([1] * len(market.days), market.next_day_returns)
    signals = daily_signals(market.days)
    rows = [row(column, signals[column.key], market, hold, short) for column in signal_service.columns()]
    labels, hold_curve = curve_points(market.days, metrics.equity_curve([1] * len(market.days), market.next_day_returns))
    rule = combining_service.current_rule()
    return {**page, "rows": sorted(rows, key=lambda r: -r["profit_pct"]), "hold": hold,
            "chart": {"labels": labels, "hold": hold_curve,
                      "lines": [{key: r[key] for key in ("key", "agent", "source", "name", "curve")} for r in rows]},
            "best": max(rows, key=lambda r: r["profit_pct"]),
            "beat_hold": sum(1 for r in rows if r["vs_hold_pct"] > 0), "rule_text": combining_service.describe(rule)}
