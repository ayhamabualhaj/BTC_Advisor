"""The Opus system prompts: each agent's prompt.md plus the shared answer format."""

from pathlib import Path

OUTPUT_INSTRUCTIONS = Path(__file__).with_name("output_instructions.md")
# Gold's agents get the same answer format with gold's own usual rate.
GOLD_OUTPUT_INSTRUCTIONS = Path(__file__).with_name("gold_output_instructions.md")


def output_instructions(prompt_file):
    gold = Path(prompt_file).parent.name.startswith("gold_")
    return GOLD_OUTPUT_INSTRUCTIONS if gold else OUTPUT_INSTRUCTIONS


def prompt_text(prompt_file):
    return Path(prompt_file).read_text().strip() + "\n" + output_instructions(prompt_file).read_text()
