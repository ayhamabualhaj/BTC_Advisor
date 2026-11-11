"""Every domain package (its setup plus rules, ML and Opus agents), by agent name.

A domain may lack an agent kind (its `rules`, `ml` or `opus` is None): financial stress has
only ML, the risk-on day only rules, the dollar only ML. Gold has its own packages
(`ai/gold_<domain>/`); `agents()` lists the ones of the asset the code is working on.
"""

from ai import (derivatives, dollar, gold_dollar, gold_macro, gold_stress, gold_technical, macro, riskon, stress,
                technical)
from apps.data import assets

DOMAINS = {package.AGENT: package for package in (technical, derivatives, macro, stress, riskon, dollar,
                                                  gold_technical, gold_macro, gold_stress, gold_dollar)}
KIND_MODULES = {"rules": "rules", "ml": "ml", "opus": "opus"}


def agents():
    """The current asset's agents, in the order the pages show them."""
    return list(assets.current().agents)


def has(agent, kind):
    """Whether a domain has an agent of this kind ("rules", "ml" or "opus")."""
    return getattr(DOMAINS[agent], KIND_MODULES[kind], None) is not None


def with_kind(kind, among=None):
    """The current asset's agents (or those given) that have this kind."""
    return [agent for agent in (among or agents()) if has(agent, kind)]
