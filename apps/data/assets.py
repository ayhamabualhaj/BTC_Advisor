"""The markets the advisor covers, and which one the running code is working on.

Everything was built for Bitcoin; gold was added beside it with its own price series, its own
agents (named "gold_<domain>", so their runs, scores and memory never mix with Bitcoin's) and
its own vote. The current asset is Bitcoin unless the code runs inside `use("gold")`: the web
pages do that for URLs under /gold/, the management commands for `--asset gold`. Reading it
from one place keeps every service free of an extra parameter.
"""

import contextlib
import contextvars
import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    key: str
    label: str            # "Bitcoin", as the pages write it
    price_source: str     # MarketData source of its daily candle
    price_prefix: str     # in front of open / high / low / close / volume
    agents: tuple         # its agents' names, in the order the pages show them
    agent_prefix: str     # in front of the domain in each agent's name
    # Bitcoin trades every day. Gold does not: its outcome "7 days later" is the first close on
    # or after that day, which can come up to this many days later (weekends, holidays).
    outcome_wait_days: int
    signals_start: datetime.date  # the first day the Signals and Profit pages show
    test_start: datetime.date     # where the vote's own test period (and the track record) starts

    @property
    def every_day(self):
        return self.outcome_wait_days == 0

    def price_field(self, field):
        return self.price_prefix + field

    def domain(self, agent):
        """An agent's domain without the asset: "gold_macro" -> "macro"."""
        return agent.removeprefix(self.agent_prefix)

    def named(self, name):
        """A stored name (BacktestRun, cache key) that belongs to this asset only."""
        return name if self.key == DEFAULT else f"{self.key}:{name}"


DEFAULT = "btc"
ASSETS = {
    "btc": Asset("btc", "Bitcoin", "binance", "", ("technical", "derivatives", "macro", "stress", "riskon", "dollar"),
                 "", 0, datetime.date(2019, 1, 1), datetime.date(2025, 1, 1)),
    "gold": Asset("gold", "Gold", "yahoo", "gold_", ("gold_technical", "gold_macro", "gold_stress", "gold_dollar"),
                  "gold_", 4, datetime.date(2010, 1, 1), datetime.date(2024, 1, 1)),
}
_current = contextvars.ContextVar("asset", default=DEFAULT)


def current():
    return ASSETS[_current.get()]


@contextlib.contextmanager
def use(key):
    """Run the enclosed code for one asset."""
    token = _current.set(ASSETS[key].key)
    try:
        yield ASSETS[key]
    finally:
        _current.reset(token)


def of_agent(agent):
    """The asset an agent belongs to."""
    return next(asset for asset in ASSETS.values() if agent in asset.agents)
