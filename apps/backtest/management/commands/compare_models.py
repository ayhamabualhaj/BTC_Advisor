from decimal import Decimal

from django.core.management.base import BaseCommand

from ai.opus_client import PRICES_PER_MTOK
from apps.backtest.services import model_comparison_service as mcs


def tally(t):
    hit = f"{t.hit_rate:5.1f}% of {t.calls:2d}" if t.hit_rate is not None else "   no calls"
    brier = f"{t.brier:.3f}" if t.brier is not None else "  -  "
    return f"{hit} calls, Brier {brier}, ${t.cost_usd:.4f}"


class Command(BaseCommand):
    help = ("Ask another Claude model exactly what Opus 5.5 was asked in its backtest and compare "
            "(PAID for the other model's calls; use --estimate first).")

    def add_arguments(self, parser):
        parser.add_argument("--model", default="claude-haiku-5-5", choices=sorted(PRICES_PER_MTOK))
        parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.50"),
                            help="Stop before spending more than this many US$ (default 0.50)")
        parser.add_argument("--estimate", action="store_true", help="Only print calls needed and cost")
        parser.add_argument("--report", action="store_true", help="Only compare runs already made (free)")

    def handle(self, *args, **options):
        model = options["model"]
        calls, cost = mcs.estimate(model)
        self.stdout.write(f"{model}: {calls} calls still to run, about ${cost:.3f}")
        if options["estimate"]:
            return
        if not options["report"] and calls:
            progress = mcs.replay(model, options["max_cost"], on_run=lambda ref, run: self.stdout.write(
                f"{run.date} {run.agent:<11} {mcs.REFERENCE} {ref.opus_score:.0f}  {model} "
                f"{run.opus_score if run.opus_score is not None else '-'}  ${run.cost_usd:.5f}"))
            self.stdout.write(f"Made {progress.calls} calls for ${progress.spent_usd:.4f}")
            for error in progress.errors:
                self.stdout.write(self.style.ERROR(error))
            if progress.stopped_at_cap:
                self.stdout.write(self.style.WARNING(f"Stopped at the ${options['max_cost']} cap."))

        for horizon in mcs.HORIZONS:
            rows = mcs.compare(model, horizon)
            if not rows:
                self.stdout.write("Nothing to compare yet.")
                return
            self.stdout.write(f"\nJudged after {horizon} day(s) (Buy >= 55, Sell <= 45):")
            for key, row in rows.items():
                self.stdout.write(f"  {key:<11} {mcs.REFERENCE:<16} {tally(row['reference'])}")
                self.stdout.write(f"  {'':<11} {model:<16} {tally(row['other'])}")
                self.stdout.write(f"  {'':<11} same side {row['same_side']}/{row['reference'].days} days, "
                                  f"mean score gap {row['gap']:.1f}")
