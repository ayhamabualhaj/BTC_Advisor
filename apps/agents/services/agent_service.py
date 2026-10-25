from apps.agents.derivatives import agent as derivatives_agent
from apps.agents.macro import agent as macro_agent
from apps.agents.technical import agent as technical_agent

AGENT_MODULES = {
    module.AGENT: module for module in (technical_agent, derivatives_agent, macro_agent)
}


def run_agents(date, agents=None, client=None, is_backtest=False):
    """Run each agent on its own; they never see each other's results."""
    return [AGENT_MODULES[agent].run(date, client, is_backtest) for agent in agents or AGENT_MODULES]
