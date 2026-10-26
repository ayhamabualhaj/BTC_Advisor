"""What one domain's agents get for a day, and what they give back."""

import datetime
from dataclasses import dataclass, field

from ai.opus_client import OpusReply
from ai.scoring import RuleScore


@dataclass
class Brief:
    agent: str
    date: datetime.date
    snapshot: dict          # indicator values known on `date` (for the rules)
    setup: dict             # the same as relative numbers (for ML and Opus)
    training: list = field(default_factory=list)  # [(features, went_up)] known by `date`
    ml_features: dict = field(default_factory=dict)  # today's numbers for the ML agent
    similar: dict | None = None  # summary of the closest past days, for Opus
    prompt_text: str = ""   # empty when Opus is not asked

    def opus_input(self):
        return {**self.setup, "similar_past_days": self.similar}


@dataclass
class Verdict:
    agent: str
    rules: RuleScore | None  # None for a domain without a rules agent
    ml: object              # ai.ml.MLScore
    opus: OpusReply | None = None  # None when Opus was not asked
