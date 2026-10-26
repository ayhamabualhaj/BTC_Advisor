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
    # Empty for a domain without a rules agent (financial stress has only an ML agent).
    rule_score = models.FloatField(null=True, blank=True)
    # Empty when the ML agent had too few past days to learn from.
    ml_score = models.FloatField(null=True, blank=True)
    # Empty for rule-only runs and when Opus failed twice (see error). Holds the score of
    # whichever Claude model ran (see model), Opus unless a comparison says otherwise.
    opus_score = models.FloatField(null=True, blank=True)
    # The Claude model asked; empty when none was.
    model = models.CharField(max_length=40, blank=True)
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
        return f"{self.date} {self.agent}: rules {self.rule_score}, ml {self.ml_score}, opus {self.opus_score}"

    def as_output(self):
        """The agent output format from the project plan."""
        key_data = {k: v for k, v in self.key_data.items() if k not in ("model_input", "rule_reasons", "ml_reasons", "skipped")}
        return {
            "agent": self.agent,
            "date": self.date.isoformat(),
            "rule_score": self.rule_score,
            "ml_score": self.ml_score,
            "opus_score": self.opus_score,
            "direction": self.direction,
            "reasons": self.reasons,
            "key_data": key_data,
            "suggested_stop_loss": self.suggested_stop_loss,
            "prompt_version": self.prompt_version.version if self.prompt_version else None,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": float(self.cost_usd),
        }
