from pathlib import Path

from apps.agents.models import PromptVersion

OUTPUT_INSTRUCTIONS = Path(__file__).resolve().parent.parent / "output_instructions.md"


def prompt_text(prompt_file):
    """The full system prompt: the agent's prompt.md plus the shared answer format."""
    return Path(prompt_file).read_text().strip() + "\n" + OUTPUT_INSTRUCTIONS.read_text()


def current_version(agent, prompt_file):
    """The PromptVersion matching the prompt files on disk.

    Editing prompt.md (or the shared instructions) creates a new version on the next run,
    so every saved result stays linked to the exact text that produced it.
    """
    text = prompt_text(prompt_file)
    latest = PromptVersion.objects.filter(agent=agent).order_by("-version").first()
    if latest and latest.prompt_text == text:
        return latest
    return PromptVersion.objects.create(
        agent=agent,
        version=latest.version + 1 if latest else 1,
        prompt_text=text,
        notes="Created automatically from prompt.md",
    )
