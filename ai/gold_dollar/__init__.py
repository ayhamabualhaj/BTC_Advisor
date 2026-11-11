from apps.agents.models import AgentName

from . import inputs, ml, rules  # noqa: F401  the domain's setup and its two agents

AGENT = AgentName.GOLD_DOLLAR
opus = None  # no LLM agent, as for Bitcoin's dollar domain
