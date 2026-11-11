from django.db import models


class AgentName(models.TextChoices):
    TECHNICAL = "technical", "Technical analysis"
    DERIVATIVES = "derivatives", "Derivatives"
    MACRO = "macro", "Macro"
    STRESS = "stress", "Financial stress"
    RISKON = "riskon", "Risk-on day"
    DOLLAR = "dollar", "Dollar"
    # Gold's agents (apps/data/assets.py): the same domains, learned and judged on gold.
    GOLD_TECHNICAL = "gold_technical", "Technical analysis"
    GOLD_MACRO = "gold_macro", "Macro"
    GOLD_STRESS = "gold_stress", "Financial stress"
    GOLD_DOLLAR = "gold_dollar", "Dollar"
