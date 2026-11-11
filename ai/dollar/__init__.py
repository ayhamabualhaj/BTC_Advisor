from apps.agents.models import AgentName

from . import inputs, ml  # noqa: F401  the domain's setup and its one agent

AGENT = AgentName.DOLLAR
# Only an ML agent, and it votes only in the strong signal (decision_rule.STRONG_ONLY): no
# rules or LLM version was tested (CLAUDE.md, "Strong signal with the dollar agent").
rules = None
opus = None
