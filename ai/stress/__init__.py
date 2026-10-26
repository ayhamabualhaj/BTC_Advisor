from apps.agents.models import AgentName

from . import inputs, ml  # noqa: F401  the domain's setup and its one agent

AGENT = AgentName.STRESS
# Only an ML agent. The rules version of this test failed and an LLM agent was never
# tested (CLAUDE.md, "Agents tested"), so this domain has no rules or LLM agent.
rules = None
opus = None
