from django.db import models

from apps.agents.models import AgentName


class DailyScore(models.Model):
    """A stored rule and ML score per day and agent, so years of history load quickly.

    `fingerprint` identifies the code that produced the scores (see score_store): when a
    rule, the ML model or an indicator changes, old rows no longer match and are rebuilt.
    """

    date = models.DateField()
    agent = models.CharField(max_length=20, choices=AgentName.choices)
    rule_score = models.FloatField()
    ml_score = models.FloatField(null=True, blank=True)
    fingerprint = models.CharField(max_length=16)

    class Meta:
        ordering = ["date", "agent"]
        constraints = [models.UniqueConstraint(fields=["date", "agent", "fingerprint"], name="one_score_per_day")]

    def __str__(self):
        return f"{self.date} {self.agent}: rules {self.rule_score:.0f}, ml {self.ml_score}"
