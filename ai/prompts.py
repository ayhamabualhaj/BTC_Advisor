"""The Opus system prompts: each agent's prompt.md plus the shared answer format."""

from pathlib import Path

OUTPUT_INSTRUCTIONS = Path(__file__).with_name("output_instructions.md")


def prompt_text(prompt_file):
    return Path(prompt_file).read_text().strip() + "\n" + OUTPUT_INSTRUCTIONS.read_text()
