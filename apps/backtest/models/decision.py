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
    threshold = models.FloatField()
    # 3 = all agents must clear the threshold, 2 = any two (to be compared by backtest).
    agents_required = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date}: {self.get_signal_display()}"
