from django.db import models


class AgentName(models.TextChoices):
    TECHNICAL = "technical", "Technical analysis"
    DERIVATIVES = "derivatives", "Derivatives"
    MACRO = "macro", "Macro"
    STRESS = "stress", "Financial stress"
    RISKON = "riskon", "Risk-on day"
