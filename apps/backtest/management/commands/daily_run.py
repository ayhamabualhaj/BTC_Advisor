import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.backtest.services import combining_service, daily_run_service


class Command(BaseCommand):
    help = ("Collect data, run the three agents for yesterday (the last full UTC day), save the "
            "decision and update outcomes. Schedule it shortly after 00:00 UTC.")

    def add_arguments(self, parser):
        parser.add_argument("--date", help="YYYY-MM-DD (default: yesterday UTC)")
        parser.add_argument("--rules-only", action="store_true", help="Skip Opus (free)")
        parser.add_argument("--force", action="store_true", help="Run again even if the date already ran")
        parser.add_argument("--no-collect", action="store_true", help="Use the data already stored")

    def handle(self, *args, **options):
        date = datetime.date.fromisoformat(options["date"]) if options["date"] else None
        try:
            report = daily_run_service.run(date, options["rules_only"], options["force"],
                                           collect=not options["no_collect"])
        except daily_run_service.DailyRunError as error:
            raise CommandError(str(error)) from error

        for source, error in report.collection_errors.items():
            self.stdout.write(self.style.WARNING(f"data {source}: {error}"))
        if not report.used_opus:
            self.stdout.write(self.style.WARNING("Rules only (no ANTHROPIC_API_KEY or --rules-only)."))
        for run in report.agent_runs:
            opus = run.opus_score if run.opus_score is not None else "-"
            ml = f"{run.ml_score:.0f}" if run.ml_score is not None else "-"
            self.stdout.write(f"{run.agent:<11} rules {run.rule_score:3.0f}  ml {ml:>3}  opus {opus:>3}  "
                              f"{run.direction:<8} ${run.cost_usd:.4f}")
            if run.error:
                self.stdout.write(self.style.ERROR(f"  {run.error}"))
        decision = report.decision
        self.stdout.write(self.style.SUCCESS(
            f"{report.date}: {decision.get_signal_display()} "
            f"({combining_service.describe(decision.rule)}; net votes {decision.net_votes:+d})"))
        self.stdout.write(f"Outcomes updated: {report.outcomes_updated}; memory cases added: {report.memory_cases}")
