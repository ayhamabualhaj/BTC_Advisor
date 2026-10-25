from django.db import models


class BacktestRun(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    # Which agent was tested ("technical", ..., or "combined") and how.
    name = models.CharField(max_length=60)
    settings = models.JSONField(default=dict, blank=True)
    trade_count = models.PositiveIntegerField(default=0)
    win_rate = models.FloatField(null=True, blank=True)
    total_profit_pct = models.FloatField(null=True, blank=True)
    max_drawdown_pct = models.FloatField(null=True, blank=True)
    buy_and_hold_pct = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} {self.start_date} to {self.end_date}"
