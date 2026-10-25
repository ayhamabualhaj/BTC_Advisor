from django.db import models


class ManualTrade(models.Model):
    """Ayham's own decision for a day, to compare with the agents."""

    class Action(models.TextChoices):
        BUY = "buy", "Buy"
        SKIP = "skip", "Skip"

    date = models.DateField()
    action = models.CharField(max_length=10, choices=Action.choices)
    entry_price = models.FloatField(null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)
    result_pct = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} manual {self.action}"
