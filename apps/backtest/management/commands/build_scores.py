import datetime

from django.core.management.base import BaseCommand

from apps.backtest.repositories import price_repository
from apps.backtest.services import score_store


class Command(BaseCommand):
    help = "Score every past day with the rule and ML agents and store it (free; minutes the first time)."

    def add_arguments(self, parser):
        parser.add_argument("--start", default="2019-01-01")
        parser.add_argument("--end", help="YYYY-MM-DD (default: the last day with a price)")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else price_repository.latest_close_date()
        days = [start + datetime.timedelta(days=n) for n in range((end - start).days + 1)]

        def progress(day):
            if day.day == 1:
                self.stdout.write(f"  {day:%Y-%m}")

        rules, _ = score_store.scores(days, on_progress=progress)
        self.stdout.write(self.style.SUCCESS(
            f"{len(rules)} days scored, fingerprint {score_store.fingerprint()} "
            f"(the last {score_store.FRESH_DAYS} days are not stored)."))
