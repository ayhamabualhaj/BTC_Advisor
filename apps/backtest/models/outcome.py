from django.db import models


class Outcome(models.Model):
    """What the price did after a decision date; filled in as the days pass."""

    date = models.DateField(unique=True)
    price_at_decision = models.FloatField()
    price_after_1d = models.FloatField(null=True, blank=True)
    price_after_3d = models.FloatField(null=True, blank=True)
    price_after_7d = models.FloatField(null=True, blank=True)
    # Empty until the 7-day price is known.
    technical_correct = models.BooleanField(null=True, blank=True)
    derivatives_correct = models.BooleanField(null=True, blank=True)
    macro_correct = models.BooleanField(null=True, blank=True)
    stress_correct = models.BooleanField(null=True, blank=True)
    riskon_correct = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} outcome"
