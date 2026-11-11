import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.backtest.repositories import price_repository
from apps.data import assets

from apps.backtest.services import combining_service, daily_run_service


class Command(BaseCommand):
    help = ("Collect data, run the agents of every market (Bitcoin, then gold) for yesterday (the "
            "last full UTC day), save the decisions and update outcomes. Schedule it shortly after 00:00 UTC.")

    def add_arguments(self, parser):
        parser.add_argument("--date", help="YYYY-MM-DD (default: yesterday UTC)")
        parser.add_argument("--rules-only", action="store_true", help="Skip Opus (free)")
        parser.add_argument("--force", action="store_true", help="Run again even if the date already ran")
        parser.add_argument("--no-collect", action="store_true", help="Use the data already stored")
        parser.add_argument("--asset", choices=sorted(assets.ASSETS), help="Only this market (default: all)")

    def handle(self, *args, **options):
        date = datetime.date.fromisoformat(options["date"]) if options["date"] else None
        collect = not options["no_collect"]
        failed = []
        for key in [options["asset"]] if options["asset"] else list(assets.ASSETS):
            with assets.use(key) as asset:
                self.stdout.write(self.style.MIGRATE_HEADING(asset.label))
                day = date or daily_run_service.last_full_day()
                if not asset.every_day and collect:
                    daily_run_service.collect_data(day)
                    collect = False
                # A market that was closed that day (gold at a weekend) has nothing to run.
                if not asset.every_day and day not in price_repository.closes(day, day):
                    self.stdout.write(f"No {asset.label} close for {day}: the market was closed, nothing to run.")
                    continue
                try:
                    self.run(day, options, collect)
                except daily_run_service.DailyRunError as error:
                    # One market failing (it already ran, say) must not stop the other.
                    self.stdout.write(self.style.ERROR(str(error)))
                    failed.append(asset.label)
            # One collection covers every market: the data is shared.
            collect = False
        if failed:
            raise CommandError(f"Not run: {', '.join(failed)}")

    def run(self, date, options, collect):
        report = daily_run_service.run(date, options["rules_only"], options["force"], collect=collect)

        for source, error in report.collection_errors.items():
            self.stdout.write(self.style.WARNING(f"data {source}: {error}"))
        if not report.used_opus:
            self.stdout.write(self.style.WARNING("Rules only (no ANTHROPIC_API_KEY or --rules-only)."))
        if report.caught_up:
            self.stdout.write(f"Also ran missed days: {', '.join(day.isoformat() for day in report.caught_up)}")
        for run in report.agent_runs:
            opus = run.opus_score if run.opus_score is not None else "-"
            ml = f"{run.ml_score:.0f}" if run.ml_score is not None else "-"
            rules = f"{run.rule_score:.0f}" if run.rule_score is not None else "-"
            self.stdout.write(f"{run.agent:<14} rules {rules:>3}  ml {ml:>3}  opus {opus:>3}  "
                              f"{run.direction:<8} ${run.cost_usd:.4f}")
            if run.error:
                self.stdout.write(self.style.ERROR(f"  {run.error}"))
        decision = report.decision
        self.stdout.write(self.style.SUCCESS(
            f"{report.date}: {decision.get_signal_display()} "
            f"({', '.join(f'{voter} {call}' for voter, call in decision.group_calls.items())}; "
            f"overall net {decision.net_votes:+d})"))
        self.stdout.write(f"Rule: {combining_service.describe(decision.rule)}")
        self.stdout.write(f"Outcomes updated: {report.outcomes_updated}; memory cases added: {report.memory_cases}")
