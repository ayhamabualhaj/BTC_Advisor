import datetime
from dataclasses import asdict

from apps.backtest import calibration
from apps.backtest.models import BacktestRun
from apps.backtest.repositories import price_repository


def calibrate(score_type, scores_by_day, horizon=calibration.HORIZON_DAYS, save=True):
    """Calibration per agent over the days in scores_by_day. Returns {agent: report}."""
    days = sorted(scores_by_day)
    closes = price_repository.closes(days[0], days[-1] + datetime.timedelta(days=horizon))
    returns = calibration.forward_returns(days, closes, horizon)
    agents = sorted({agent for scores in scores_by_day.values() for agent in scores})
    reports = {}
    for agent in agents:
        pairs = [(scores_by_day[day][agent], returns[day]) for day in days
                 if day in returns and scores_by_day[day].get(agent) is not None]
        report = {
            "horizon_days": horizon,
            "calls": sum(1 for score, _ in pairs if score != 50),
            "brier_score": calibration.brier_score(pairs),
            "buckets": [asdict(bucket) for bucket in calibration.calibration_table(pairs)],
        }
        reports[agent] = report
        if save and pairs:
            BacktestRun.objects.create(
                name=f"{score_type}:{agent}:calibration",
                start_date=days[0],
                end_date=days[-1],
                settings={"score_type": score_type, "agent": agent, **report},
            )
    return reports
