from django.db import models


class MarketData(models.Model):
    """One daily number from one source, e.g. (2026-07-01, binance, close, 61234.5).

    A long "date / source / field / value" table so new data series need no migration.
    """

    date = models.DateField()
    source = models.CharField(max_length=40)
    field = models.CharField(max_length=60)
    value = models.FloatField()
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "source", "field"]
        constraints = [
            models.UniqueConstraint(fields=["date", "source", "field"], name="unique_market_data_point"),
        ]
        indexes = [models.Index(fields=["source", "field", "date"])]

    def __str__(self):
        return f"{self.date} {self.source}.{self.field} = {self.value}"
