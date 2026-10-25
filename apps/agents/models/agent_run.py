from django.db import models

from .agent_name import AgentName
from .prompt_version import PromptVersion


class AgentRun(models.Model):
    """One agent's verdict for one decision date (live or inside a backtest)."""

    class Direction(models.TextChoices):
        BULLISH = "bullish", "Bullish"
        BEARISH = "bearish", "Bearish"
        NEUTRAL = "neutral", "Neutral"

    date = models.DateField()
    agent = models.CharField(max_length=20, choices=AgentName.choices)
    rule_score = models.FloatField()
    # Empty for rule-only runs and when Opus failed twice (see error).
    opus_score = models.FloatField(null=True, blank=True)
    direction = models.CharField(max_length=10, choices=Direction.choices, blank=True)
    reasons = models.JSONField(default=list, blank=True)
    key_data = models.JSONField(default=dict, blank=True)
    suggested_stop_loss = models.FloatField(null=True, blank=True)
    prompt_version = models.ForeignKey(
        PromptVersion, on_delete=models.PROTECT, null=True, blank=True, related_name="runs"
    )
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    is_backtest = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "agent"]
        indexes = [models.Index(fields=["agent", "date"])]

    def __str__(self):
        return f"{self.date} {self.agent}: rules {self.rule_score:.0f}, opus {self.opus_score}"
