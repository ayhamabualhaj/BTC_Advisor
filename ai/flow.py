"""The daily run as a CrewAI Flow: the rule, ML and Opus agents of every domain.

The three kinds of agent start together and never see each other's results; the last step
gathers one Verdict per domain. CrewAI runs the steps on a worker thread, so they only
compute and call Opus: the services build the Briefs from the database beforehand and save
the Verdicts afterwards.
"""

from typing import Any

from crewai.flow.flow import Flow, and_, listen, start
from pydantic import BaseModel, ConfigDict

from ai.brief import Verdict
from ai.domains import DOMAINS, has


class AdvisorState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    briefs: dict[str, Any] = {}
    use_opus: bool = False
    rules: dict[str, Any] = {}
    ml: dict[str, Any] = {}
    opus: dict[str, Any] = {}


class AdvisorFlow(Flow[AdvisorState]):
    def __init__(self, client=None):
        super().__init__(suppress_flow_events=True)
        self.client = client  # the Anthropic client (a fake one in tests)

    @start()
    def rule_agents(self):
        self.state.rules = {agent: DOMAINS[agent].rules.score(brief.snapshot)
                            for agent, brief in self.state.briefs.items() if has(agent, "rules")}

    @start()
    def ml_agents(self):
        self.state.ml = {agent: DOMAINS[agent].ml.score(brief) for agent, brief in self.state.briefs.items()}

    @start()
    def opus_agents(self):
        if self.state.use_opus:
            self.state.opus = {agent: DOMAINS[agent].opus.judge(brief, self.client)
                               for agent, brief in self.state.briefs.items() if has(agent, "opus")}

    @listen(and_(rule_agents, ml_agents, opus_agents))
    def verdicts(self):
        return [Verdict(agent, self.state.rules.get(agent), self.state.ml[agent], self.state.opus.get(agent))
                for agent in self.state.briefs]


def run(briefs, use_opus, client=None):
    """{agent: Brief} in, [Verdict] out, in the briefs' order."""
    return AdvisorFlow(client).kickoff(inputs={"briefs": briefs, "use_opus": use_opus})
