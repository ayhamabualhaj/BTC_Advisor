from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.data.collectors import etf_flows
from apps.data.collectors.base import CollectorError
from apps.data.repositories import market_data_repository


class Command(BaseCommand):
    help = "Import spot Bitcoin ETF daily net flows from farside.co.uk's table (CSV or pasted text)."

    def add_arguments(self, parser):
        parser.add_argument("csv_file")

    def handle(self, *args, **options):
        path = Path(options["csv_file"])
        if not path.exists():
            raise CommandError(f"{path} not found")
        try:
            points = etf_flows.parse_csv(path.read_text(encoding="utf-8-sig").splitlines())
        except CollectorError as error:
            raise CommandError(str(error)) from error
        count = market_data_repository.save_points(etf_flows.SOURCE, points)
        self.stdout.write(self.style.SUCCESS(f"Saved {count} days of ETF flows"))
