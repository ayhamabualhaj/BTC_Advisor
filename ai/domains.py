"""Every domain package (its setup plus rules, ML and Opus agents), by agent name."""

from ai import derivatives, macro, technical

DOMAINS = {package.AGENT: package for package in (technical, derivatives, macro)}
