import datetime
import json

from apps.data.management.asset_command import AssetCommand

from ai.domains import DOMAINS
from apps.agents.services import agent_service


class Command(AssetCommand):
    help = "Run every domain's rule, ML and Opus agent for a date and print the JSON. Costs API money."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--date", help="YYYY-MM-DD (default: yesterday, the last full day)")
        parser.add_argument("--agent", action="append", choices=list(DOMAINS))

    def handle(self, *args, **options):
        yesterday = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)
        date = datetime.date.fromisoformat(options["date"]) if options["date"] else yesterday
        for run in agent_service.run_agents(date, options["agent"]):
            self.stdout.write(json.dumps(run.as_output(), indent=2))
            if run.error:
                self.stdout.write(self.style.ERROR(f"{run.agent}: {run.error}"))
