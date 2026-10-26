import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.agents.models import AgentName
from apps.backtest.services import backtest_service, opus_backtest_service, score_history

from ._report import format_hold, format_run
from .backtest_rules import TEST_START


class Command(BaseCommand):
    help = ("Backtest the Opus agents day by day (PAID: one API call per agent per day). "
            "Resumes where it stopped; use --estimate first.")

    def add_arguments(self, parser):
        parser.add_argument("--start", default=TEST_START)
        parser.add_argument("--end", help="YYYY-MM-DD (default: last day with a known next-day price)")
        parser.add_argument("--agent", action="append", choices=AgentName.values)
        parser.add_argument("--max-cost", type=Decimal, default=Decimal("5.00"),
                            help="Stop before spending more than this many US$ (default 5)")
        parser.add_argument("--estimate", action="store_true", help="Only print calls needed and cost")
        parser.add_argument("--threshold", type=float, default=backtest_service.DEFAULT_THRESHOLD)
        parser.add_argument("--min-votes", type=int, default=1, help="combined: Buy votes must lead by this many")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else datetime.date.today()
        market = backtest_service.load_market(start, end)
        if not market.days:
            raise CommandError("No price data in this period; run collect_data first.")
        agents = options["agent"] or AgentName.values

        calls, cost = opus_backtest_service.estimate(agents, market.days)
        self.stdout.write(f"{len(market.days)} days x {len(agents)} agents: {calls} calls still to run, "
                          f"about ${cost:.2f}")
        if options["estimate"]:
            return

        progress = opus_backtest_service.run(
            agents, market.days, options["max_cost"],
            on_run=lambda run: self.stdout.write(
                f"{run.date} {run.agent:<11} opus {run.opus_score}  rules {run.rule_score:.0f}  ${run.cost_usd:.4f}"),
        )
        self.stdout.write(f"Made {progress.calls} calls for ${progress.spent_usd:.2f}")
        for error in progress.errors:
            self.stdout.write(self.style.ERROR(error))
        if progress.stopped_at_cap:
            self.stdout.write(self.style.WARNING(
                f"Stopped at the ${options['max_cost']} cap; run again (with a higher --max-cost) to continue."))
            return

        versions = opus_backtest_service.prompt_versions(agents)
        scores = score_history.opus_scores(market.days, versions)
        runs = backtest_service.run_backtest("opus", scores, market, options["threshold"], options["min_votes"])
        for run in runs:
            run.settings["prompt_versions"] = {agent: version.version for agent, version in versions.items()}
            run.save()
            self.stdout.write(format_run(run))
        self.stdout.write(format_hold(runs[0]))
