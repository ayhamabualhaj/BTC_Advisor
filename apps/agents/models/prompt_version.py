from django.db import models

from .agent_name import AgentName


class PromptVersionLocked(Exception):
    """Raised when code tries to change the text of a saved prompt version."""


class PromptVersion(models.Model):
    agent = models.CharField(max_length=20, choices=AgentName.choices)
    version = models.PositiveIntegerField()
    prompt_text = models.TextField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["agent", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["agent", "version"], name="unique_prompt_version"),
        ]

    def save(self, *args, **kwargs):
        # Results are linked to a version, so its text must never change afterwards:
        # a changed prompt has to be saved as a new version.
        if self.pk is not None:
            saved_text = PromptVersion.objects.filter(pk=self.pk).values_list("prompt_text", flat=True).first()
            if saved_text is not None and saved_text != self.prompt_text:
                raise PromptVersionLocked(f"{self} is saved; create a new version instead.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.agent} prompt v{self.version}"
