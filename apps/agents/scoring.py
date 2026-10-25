"""Shared pieces of the rule-based scores: start at 50, criteria add or subtract."""

from dataclasses import dataclass, field

BASE_SCORE = 50
BULLISH_AT = 55
BEARISH_AT = 45


@dataclass
class RuleScore:
    # (reason, points) for every criterion that fired.
    contributions: list = field(default_factory=list)
    # Criteria that could not be judged because their data is missing.
    skipped: list = field(default_factory=list)

    def add(self, reason, points):
        self.contributions.append((reason, points))

    def skip(self, criterion):
        self.skipped.append(criterion)

    @property
    def score(self):
        total = BASE_SCORE + sum(points for _, points in self.contributions)
        return max(0, min(100, total))

    @property
    def direction(self):
        if self.score >= BULLISH_AT:
            return "bullish"
        if self.score <= BEARISH_AT:
            return "bearish"
        return "neutral"

    @property
    def reasons(self):
        return [f"{reason} ({points:+d})" for reason, points in self.contributions]


def has(snapshot, *keys):
    return all(snapshot.get(key) is not None for key in keys)
