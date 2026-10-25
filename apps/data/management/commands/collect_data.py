import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.data.services import collection_service


class Command(BaseCommand):
    help = "Pull daily market data from every source into MarketData, then report missing days."

    def add_arguments(self, parser):
        parser.add_argument("--start", default=settings.DATA_START_DATE, help="YYYY-MM-DD")
        parser.add_argument("--end", help="YYYY-MM-DD (default: yesterday, the last full day)")
        parser.add_argument("--source", action="append", choices=sorted(collection_service.COLLECTORS),
                            help="Only this source (can be repeated)")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        yesterday = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else yesterday
        if start > end:
            raise CommandError("--start is after --end")

        result = collection_service.collect(start, end, options["source"])
        for source, count in result.saved.items():
            self.stdout.write(self.style.SUCCESS(f"{source}: saved {count} points"))
        for source, error in result.errors.items():
            self.stdout.write(self.style.ERROR(f"{source}: {error}"))

        for (source, field), days in collection_service.missing_days(start, end, options["source"]).items():
            shown = ", ".join(day.isoformat() for day in days[:5])
            more = f" (+{len(days) - 5} more)" if len(days) > 5 else ""
            self.stdout.write(self.style.WARNING(f"missing {source}.{field}: {len(days)} days: {shown}{more}"))
