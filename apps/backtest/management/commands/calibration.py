import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.backtest import calibration
from apps.backtest.services import backtest_service, calibration_service, score_history

from .backtest_rules import TEST_START


class Command(BaseCommand):
    help = "Calibration check: for each confidence band, how often were the calls right?"

    def add_arguments(self, parser):
        parser.add_argument("--scores", choices=["rules", "ml", "opus"], default="rules")
        parser.add_argument("--start", default=TEST_START)
        parser.add_argument("--end")
        parser.add_argument("--horizon", type=int, default=calibration.HORIZON_DAYS)
        parser.add_argument("--no-save", action="store_true")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else datetime.date.today()
        days = backtest_service.load_market(start, end).days
        if not days:
            raise CommandError("No price data in this period; run collect_data first.")
        scores = score_history.scores(options["scores"], days)

        reports = calibration_service.calibrate(options["scores"], scores, options["horizon"],
                                                save=not options["no_save"])
        for agent, report in reports.items():
            brier = f"{report['brier_score']:.3f}" if report["brier_score"] is not None else "-"
            self.stdout.write(self.style.SUCCESS(
                f"{options['scores']}:{agent}  {report['calls']} calls, {report['horizon_days']}-day horizon, "
                f"Brier {brier} (always-50 = 0.250)"))
            for bucket in report["buckets"]:
                self.stdout.write(f"  {bucket['label']}: {bucket['calls']:3d} calls, right {bucket['hit_rate']:5.1f}% "
                                  f"(said {bucket['avg_confidence']:.0f}%)")
