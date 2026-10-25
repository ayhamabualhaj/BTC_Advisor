import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.backtest.services import backtest_service, score_history

from ._report import format_hold, format_run

# The first day after Opus 5.5's training cutoff (June 2026): the honest test period.
TEST_START = "2026-07-01"


class Command(BaseCommand):
    help = "Backtest the rule-based scores (free, no AI): each agent alone and combined."

    def add_arguments(self, parser):
        parser.add_argument("--start", default=TEST_START)
        parser.add_argument("--end", help="YYYY-MM-DD (default: last day with a known next-day price)")
        parser.add_argument("--threshold", type=float, default=backtest_service.DEFAULT_THRESHOLD)
        parser.add_argument("--agents-required", type=int, default=3, choices=[1, 2, 3])
        parser.add_argument("--no-save", action="store_true")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else datetime.date.today()
        market = backtest_service.load_market(start, end)
        if not market.days:
            raise CommandError("No price data in this period; run collect_data first.")

        scores = score_history.rule_scores(market.days)
        runs = backtest_service.run_backtest(
            "rules", scores, market, options["threshold"], options["agents_required"],
            save=not options["no_save"],
        )
        self.stdout.write(f"Rules backtest {market.days[0]} to {market.days[-1]} "
                          f"({len(market.days)} days), buy when score >= {options['threshold']:g}")
        for run in runs:
            self.stdout.write(format_run(run))
        self.stdout.write(format_hold(runs[0]))
