"""Read-only summaries shared by the REST API and the web pages."""

import datetime

from apps.backtest import calibration
from apps.backtest.repositories import price_repository
from apps.dashboard.repositories import report_repository


def today():
    """The latest decision and the agent runs behind it (or the latest runs if no decision yet)."""
    decision = report_repository.latest_decision()
    date = decision.date if decision else report_repository.latest_live_date()
    runs = report_repository.latest_live_runs(date) if date else []
    return {"date": date, "decision": decision, "agent_runs": runs}


def costs():
    rows = report_repository.cost_by_agent()
    total = sum(row["cost_usd"] for row in rows)
    return {"total_usd": total, "by_agent": rows, "by_day": report_repository.cost_by_day()}


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
