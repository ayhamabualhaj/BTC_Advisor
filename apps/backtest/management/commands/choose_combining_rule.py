import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.backtest.calibration import forward_returns
from apps.backtest.repositories import price_repository
from apps.agents.models import AgentName
from apps.backtest.services import backtest_service, combining_service as cs, opus_backtest_service, score_history, score_store


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
        # The LLM (AI_MODEL, current prompt) has no 2019-24 scores, so it never affects the
        # choice; in the test period its vote joins round 2 as it does live.
        versions = opus_backtest_service.prompt_versions(AgentName.values)
        llm = score_history.opus_scores(market.days, versions)
        llm_days = sum(1 for day in market.days if any(score is not None for score in llm[day].values()))
        found, chosen = cs.choose({"rules": rules, "ml": ml, "opus": llm}, market, returns_7d, end,
                                  save=not options["no_save"])
        self.stdout.write(f"LLM vote: {settings.AI_MODEL}, prompt "
                          f"{', '.join(f'{a} v{v.version}' for a, v in versions.items())}: scores on {llm_days} days.")

        self.stdout.write(f"Chosen on {cs.TUNE_START} - {cs.TUNE_END}; tested on {cs.TEST_START} - {end}.")
        for c in found:
            mark = "  <- chosen" if c is chosen else ""
            self.stdout.write(f"group lead {c.group_lead}, overall: all agree{mark}")
            self.stdout.write(f"   tuning  {line(c.tuning)}")
            self.stdout.write(f"   test    {line(c.test)}")
            test = cs.split(market, cs.TEST_START, end)
            without = cs.evaluate(c.rule, {"rules": rules, "ml": ml}, *test, returns_7d)
            self.stdout.write(f"   test without the LLM vote  {line(without)}")
        if chosen is None:
            self.stdout.write(self.style.WARNING(f"No vote made {cs.MIN_CALLS}+ calls; using {cs.DEFAULT_RULE}."))
