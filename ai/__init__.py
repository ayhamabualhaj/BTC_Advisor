"""The AI layer, kept outside the Django apps.

Three domains (technical, derivatives, macro), each with three agents that share one idea
of what matters but judge it differently:

- rules.py: explicit criteria computed in code (the rule score);
- ml.py:    logistic regression on the domain's setup numbers, retrained walk-forward;
- opus.py:  Claude Opus 5.5's judgment of the same setup (prompt.md).

flow.py runs them with a CrewAI Flow. Nothing here reads or writes the database: the
services in apps/agents prepare each agent's Brief and save the verdicts.
"""
