import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from ai.opus_client import PRICES_PER_MTOK
from apps.backtest.repositories import price_repository
from apps.backtest.services import prompt_comparison_service as pcs


def tally(t):
    hit = f"{t.hit_rate:5.1f}% of {t.calls:4d}" if t.hit_rate is not None else "   no calls"
    brier = f"{t.brier:.4f}" if t.brier is not None else "  -   "
    return f"{hit} calls, Brier {brier}"


class Command(BaseCommand):
    help = ("Ask one model the same days with two prompt versions (each with its own input) and "
            "compare them (PAID; use --estimate first). Resumes where it stopped.")

    def add_arguments(self, parser):
        parser.add_argument("--model", default="claude-haiku-5-5", choices=sorted(PRICES_PER_MTOK))
        parser.add_argument("--old", type=int, default=2)
        parser.add_argument("--new", type=int, default=3)
        parser.add_argument("--start", default="2025-01-01")
        parser.add_argument("--end", help="default: the last day with a known 7-day outcome")
        parser.add_argument("--max-cost", type=Decimal, default=Decimal("3.00"))
        parser.add_argument("--estimate", action="store_true")
        parser.add_argument("--report", action="store_true", help="Only compare what was already asked (free)")

    def handle(self, *args, **options):
        if options["old"] != 2:
            raise CommandError("Only v2's old input is kept (ai/inputs_v2.py).")
        start = datetime.date.fromisoformat(options["start"])
        last = price_repository.latest_close_date() - datetime.timedelta(days=7)
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else last
        closes = price_repository.closes(start, end)
        days = sorted(day for day in closes if start <= day <= end)
        model = options["model"]
        found = pcs.versions(options["old"], options["new"])

        work = pcs.pending(model, found, days)
        self.stdout.write(f"{model}, v{options['old']} vs v{options['new']}, {days[0]} - {days[-1]}: "
                          f"{len(work)} calls still to run, about ${pcs.per_call(model) * len(work):.2f}")
        if options["estimate"]:
            return
        if work and not options["report"]:
            counter = {"n": 0}

            def report(run):
                counter["n"] += 1
                if counter["n"] % 200 == 0:
                    self.stdout.write(f"  {counter['n']} calls done (last: {run.date})", ending="\n")
                    self.stdout.flush()

            progress = pcs.run(model, found, days, options["max_cost"], on_run=report)
            self.stdout.write(f"Made {progress.calls} calls for ${progress.spent_usd:.3f}")
            for error in progress.errors[:20]:
                self.stdout.write(self.style.ERROR(error))
            if len(progress.errors) > 20:
                self.stdout.write(self.style.ERROR(f"... {len(progress.errors) - 20} more errors"))
            if progress.stopped_at_cap:
                self.stdout.write(self.style.WARNING(f"Stopped at the ${options['max_cost']} cap; run again to continue."))

        for side in ("old", "new"):
            for agent, version in found[side].items():
                spread = pcs.score_spread(model, version, days)
                if spread:
                    self.stdout.write(f"v{version.version} {agent:<11} {spread['days']:4d} days: Sell {spread['sell']:4.1f}% "
                                      f"Hold {spread['hold']:4.1f}% Buy {spread['buy']:4.1f}%")
        for horizon in (7, 3, 1):
            result = pcs.compare(model, found, days, horizon)
            self.stdout.write(f"\nJudged after {horizon} day(s), Buy >= 55, Sell <= 45:")
            for period, rows in result.items():
                for key, row in rows.items():
                    self.stdout.write(f"  {period:<4} {key:<11} v{options['old']} {tally(row['old'])} | "
                                      f"v{options['new']} {tally(row['new'])}")
