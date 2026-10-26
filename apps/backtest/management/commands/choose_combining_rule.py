import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.backtest.calibration import forward_returns
from apps.backtest.repositories import price_repository
from apps.backtest.services import backtest_service, combining_service as cs, score_store


def line(result):
    hit = f"{result.hit_rate:5.1f}%" if result.hit_rate is not None else "    -"
    return (f"{hit} of {result.calls:4d} calls | buy days {result.buy_days:4d}, profit {result.profit_pct:+8.1f}% "
            f"(hold {result.hold_pct:+8.1f}%), drawdown {result.drawdown_pct:5.1f}%")


class Command(BaseCommand):
    help = "Choose the two-round vote's group lead on 2019-2024 and test it once on 2025 onward (free)."

    def add_arguments(self, parser):
        parser.add_argument("--no-save", action="store_true")

    def handle(self, *args, **options):
        end = price_repository.latest_close_date()
        market = backtest_service.load_market(cs.TUNE_START, end)
        if not market.days:
            raise CommandError("No price data; run collect_data first.")
        rules, ml = score_store.scores(market.days)
        closes = price_repository.closes(cs.TUNE_START, end)
        returns_7d = forward_returns(market.days, closes)
        found, chosen = cs.choose({"rules": rules, "ml": ml}, market, returns_7d, end, save=not options["no_save"])

        self.stdout.write(f"Chosen on {cs.TUNE_START} - {cs.TUNE_END}; tested on {cs.TEST_START} - {end}.")
        for c in found:
            mark = "  <- chosen" if c is chosen else ""
            self.stdout.write(f"group lead {c.group_lead}, overall: all agree{mark}")
            self.stdout.write(f"   tuning  {line(c.tuning)}")
            self.stdout.write(f"   test    {line(c.test)}")
        if chosen is None:
            self.stdout.write(self.style.WARNING(f"No vote made {cs.MIN_CALLS}+ calls; using {cs.DEFAULT_RULE}."))
