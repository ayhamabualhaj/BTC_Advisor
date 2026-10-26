from apps.agents.models import AgentName

from . import inputs, rules  # noqa: F401  the domain's setup and its one agent

AGENT = AgentName.RISKON
# Only a rules agent: the ML version of this test failed (51-52%, Oct 2026) and an LLM agent
# was never tested, so this domain has no ML or LLM agent.
ml = None
opus = None
