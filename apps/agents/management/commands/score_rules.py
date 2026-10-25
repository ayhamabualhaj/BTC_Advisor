import datetime

from django.core.management.base import BaseCommand

from apps.agents.services import rule_scoring_service


class Command(BaseCommand):
    help = "Print (and optionally save) the rule-based score of every agent for a date."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="YYYY-MM-DD (default: yesterday, the last full day)")
        parser.add_argument("--save", action="store_true", help="Store the results as AgentRuns")

    def handle(self, *args, **options):
        yesterday = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=1)
        date = datetime.date.fromisoformat(options["date"]) if options["date"] else yesterday
        results = rule_scoring_service.run_rules(date, save=options["save"])
        for agent, (_, rule_score) in results.items():
            self.stdout.write(self.style.SUCCESS(f"{agent}: {rule_score.score} ({rule_score.direction})"))
            for reason in rule_score.reasons:
                self.stdout.write(f"  {reason}")
            if rule_score.skipped:
                self.stdout.write(self.style.WARNING(f"  no data: {', '.join(rule_score.skipped)}"))
