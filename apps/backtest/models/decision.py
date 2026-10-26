from django.db import models


class Decision(models.Model):
    """The combined signal for one day, built from the three agents' scores."""

    class Signal(models.TextChoices):
        BUY = "buy", "Buy"
        NO_TRADE = "no_trade", "No trade"

    date = models.DateField()
    technical_score = models.FloatField(null=True, blank=True)
    derivatives_score = models.FloatField(null=True, blank=True)
    macro_score = models.FloatField(null=True, blank=True)
    signal = models.CharField(max_length=10, choices=Signal.choices)
    # The vote that made the decision: {"sources": [...], "min_net_votes": n}, and its result.
    rule = models.JSONField(default=dict, blank=True)
    net_votes = models.SmallIntegerField(null=True, blank=True)
    # Used by the threshold rule before the vote; kept for old decisions.
    threshold = models.FloatField(null=True, blank=True)
    agents_required = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date}: {self.get_signal_display()}"
