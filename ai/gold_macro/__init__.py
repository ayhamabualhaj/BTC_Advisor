from apps.agents.models import AgentName

from . import inputs, ml, opus  # noqa: F401  the domain's setup and its two agents

AGENT = AgentName.GOLD_MACRO
# No rules agent: none of the macro numbers passed the pattern screen on 2005-2019
# (CLAUDE.md, "Gold"), and a rule that never fires would only add a permanent Hold.
rules = None
