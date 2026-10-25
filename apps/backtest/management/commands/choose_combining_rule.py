import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.agents.models import AgentName
from apps.backtest.services import backtest_service, combining_service, opus_backtest_service, score_history

from .backtest_rules import TEST_START


class Command(BaseCommand):
    help = "Try combining-rule thresholds (all three or two agents above X) and keep the best."

    def add_arguments(self, parser):
        parser.add_argument("--scores", choices=["rules", "opus"], default="rules")
        parser.add_argument("--start", default=TEST_START)
        parser.add_argument("--end")
        parser.add_argument("--no-save", action="store_true")

    def handle(self, *args, **options):
        start = datetime.date.fromisoformat(options["start"])
        end = datetime.date.fromisoformat(options["end"]) if options["end"] else datetime.date.today()
        market = backtest_service.load_market(start, end)
        if not market.days:
            raise CommandError("No price data in this period; run collect_data first.")
        if options["scores"] == "rules":
            scores = score_history.rule_scores(market.days)
        else:
            scores = score_history.opus_scores(market.days, opus_backtest_service.prompt_versions(AgentName.values))

        candidates, chosen = combining_service.choose(options["scores"], scores, market, save=not options["no_save"])
        self.stdout.write("rule            trades   win   profit  drawdown  1st half  2nd half")
        for c in candidates:
            p = c.performance
            win = f"{p.win_rate:4.0f}%" if p.win_rate is not None else "    -"
            mark = " <- chosen" if c is chosen else ""
            self.stdout.write(f"{c.agents_required} agents >= {c.threshold}  {p.trade_count:5d}  {win}  "
                              f"{p.total_profit_pct:+7.2f}%  {p.max_drawdown_pct:6.2f}%  "
                              f"{c.first_half_pct:+7.2f}%  {c.second_half_pct:+7.2f}%{mark}")
        if chosen is None:
            self.stdout.write(self.style.WARNING(
                f"No rule made {combining_service.MIN_TRADES}+ trades; keeping the default "
                f"{combining_service.DEFAULT_RULE}."))
