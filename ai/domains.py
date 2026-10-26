"""Every domain package (its setup plus rules, ML and Opus agents), by agent name.

A domain may lack an agent kind (its `rules` or `opus` is None): financial stress has only ML.
"""

from ai import derivatives, macro, stress, technical

DOMAINS = {package.AGENT: package for package in (technical, derivatives, macro, stress)}
KIND_MODULES = {"rules": "rules", "ml": "ml", "opus": "opus"}


def has(agent, kind):
    """Whether a domain has an agent of this kind ("rules", "ml" or "opus")."""
    return getattr(DOMAINS[agent], KIND_MODULES[kind], None) is not None


def with_kind(kind, agents=None):
    return [agent for agent in (agents or DOMAINS) if has(agent, kind)]
