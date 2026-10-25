"""A stand-in for anthropic.Anthropic so tests never call the paid API."""

import json
from types import SimpleNamespace

GOOD_VERDICT = {
    "opus_score": 62,
    "direction": "bullish",
    "reasons": ["Price holds above both averages", "RSI is neutral", "Support is close below"],
    "suggested_stop_loss_pct": 5.0,
}


def response(payload=GOOD_VERDICT, stop_reason="end_turn", input_tokens=1000, output_tokens=500):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class FakeClient:
    """Returns the queued responses in order (the last one repeats) and records each call."""

    def __init__(self, *responses):
        self.responses = list(responses) or [response()]
        self.calls = []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        next_response = self.responses[min(len(self.calls), len(self.responses)) - 1]
        if isinstance(next_response, Exception):
            raise next_response
        return next_response
