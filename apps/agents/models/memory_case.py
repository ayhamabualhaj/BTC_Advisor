from django.db import models

from .agent_name import AgentName


class MemoryCase(models.Model):
    """A past setup and how it turned out, retrieved by similarity (RAG)."""

    date = models.DateField()
    agent = models.CharField(max_length=20, choices=AgentName.choices)
    setup_summary = models.TextField()
    # {feature: float} from ai/similarity.py: the setup's own numbers serve as its embedding.
    embedding = models.JSONField(default=list, blank=True)
    # {feature: float} the domain's ML agent learns from (ai/<domain>/ml.py features()).
    ml_features = models.JSONField(default=dict, blank=True)
    outcome = models.TextField(blank=True)
    return_7d_pct = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "agent"]
        constraints = [
            models.UniqueConstraint(fields=["date", "agent"], name="unique_memory_case"),
        ]

    def __str__(self):
        return f"{self.date} {self.agent} memory"
