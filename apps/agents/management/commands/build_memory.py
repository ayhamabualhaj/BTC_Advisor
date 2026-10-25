import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.agents.memory import memory_service
from apps.agents.models import AgentName
from apps.agents.services.agent_service import AGENT_MODULES


class Command(BaseCommand):
    help = "Store each past day's setup and 7-day outcome per agent as RAG memory (free, no AI)."

    def add_arguments(self, parser):
        parser.add_argument("--start", default=settings.DATA_START_DATE)
        parser.add_argument("--end", help="YYYY-MM-DD (default: yesterday UTC)")
        parser.add_argument("--agent", action="append", choices=AgentName.values)

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        yesterday = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else yesterday
        for agent in options["agent"] or AgentName.values:
            count = memory_service.build_cases(agent, AGENT_MODULES[agent].model_input, start, end)
            self.stdout.write(self.style.SUCCESS(f"{agent}: {count} memory cases"))
