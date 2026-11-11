import datetime


from apps.backtest.repositories import price_repository
from apps.backtest.services import score_store
from apps.data import assets
from apps.data.management.asset_command import AssetCommand


class Command(AssetCommand):
    help = "Score every past day with the rule and ML agents and store it (free; minutes the first time)."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--start", help="YYYY-MM-DD (default: where the asset's Signals page starts)")
        parser.add_argument("--end", help="YYYY-MM-DD (default: the last day with a price)")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"]) if options["start"] else assets.current().signals_start
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else price_repository.latest_close_date()
        # Only days the market traded: gold has no weekends.
        days = sorted(price_repository.closes(start, end))

        def progress(day):
            if day.day == 1:
                self.stdout.write(f"  {day:%Y-%m}")

        rules, _ = score_store.scores(days, on_progress=progress)
        self.stdout.write(self.style.SUCCESS(
            f"{len(rules)} days scored, fingerprint {score_store.fingerprint()} "
            f"(the last {score_store.FRESH_DAYS} days are not stored)."))
