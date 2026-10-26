"""Derivatives Opus agent: Claude Opus 5.5 judges the same setup (prompt.md)."""

from pathlib import Path

from ai import opus_client

PROMPT_FILE = Path(__file__).with_name("prompt.md")


def judge(brief, client=None):
    """Opus sees the setup and the closest past setups, never the other agents' scores."""
    return opus_client.ask(brief.prompt_text, brief.opus_input(), client)
