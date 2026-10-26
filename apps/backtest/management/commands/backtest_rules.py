import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.backtest.services import backtest_service, score_history

from ._report import format_hold, format_run

# The first day after Opus 5.5's training cutoff (June 2026): the honest test period.
TEST_START = "2026-07-01"


class Command(BaseCommand):
    help = "Backtest the rule or ML scores (free, no API calls): each agent alone and combined."

    def add_arguments(self, parser):
        parser.add_argument("--scores", choices=["rules", "ml"], default="rules")
        parser.add_argument("--start", default=TEST_START)
        parser.add_argument("--end", help="YYYY-MM-DD (default: last day with a known next-day price)")
        parser.add_argument("--threshold", type=float, default=backtest_service.DEFAULT_THRESHOLD)
        parser.add_argument("--min-votes", type=int, default=1, help="combined: Buy votes must lead by this many")
        parser.add_argument("--no-save", action="store_true")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else datetime.date.today()
        market = backtest_service.load_market(start, end)
        if not market.days:
            raise CommandError("No price data in this period; run collect_data first.")

        scores = score_history.scores(options["scores"], market.days)
        runs = backtest_service.run_backtest(
            options["scores"], scores, market, options["threshold"], options["min_votes"],
            save=not options["no_save"],
        )
        self.stdout.write(f"{options['scores']} backtest {market.days[0]} to {market.days[-1]} "
                          f"({len(market.days)} days), buy when score >= {options['threshold']:g}")
        for run in runs:
            self.stdout.write(format_run(run))
        self.stdout.write(format_hold(runs[0]))
