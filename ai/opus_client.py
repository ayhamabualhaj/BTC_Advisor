"""The one place that calls the Anthropic API. Plain SDK calls, no agent framework."""

import json
from dataclasses import dataclass
from decimal import Decimal

import anthropic
from django.conf import settings

# US$ per million tokens for Claude Opus 5.5 (Anthropic API, October 2026).
# Thinking tokens are billed and reported as output tokens.
INPUT_PRICE_PER_MTOK = Decimal("4.00")
OUTPUT_PRICE_PER_MTOK = Decimal("20.00")
MAX_TOKENS = 16000
ATTEMPTS = 2  # the plan: invalid output is retried once, then logged as an error

DIRECTIONS = ["bullish", "bearish", "neutral"]
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "opus_score": {"type": "integer"},
        "direction": {"type": "string", "enum": DIRECTIONS},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "suggested_stop_loss_pct": {"type": "number"},
    },
    "required": ["opus_score", "direction", "reasons", "suggested_stop_loss_pct"],
    "additionalProperties": False,
}


class InvalidReply(Exception):
    pass


@dataclass
class OpusReply:
    data: dict | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    error: str = ""


def make_client():
    # An empty key lets the SDK fall back to its other credential sources.
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)


def cost_usd(input_tokens, output_tokens):
    return (input_tokens * INPUT_PRICE_PER_MTOK + output_tokens * OUTPUT_PRICE_PER_MTOK) / 1_000_000


def ask(system_prompt, model_input, client=None):
    """Send the agent's data, get its verdict back as validated JSON.

    Tokens and cost add up over both attempts, since both are paid for.
    """
    client = client or make_client()
    reply = OpusReply(data=None)
    user_message = json.dumps(model_input, indent=1, sort_keys=True)
    for _ in range(ATTEMPTS):
        try:
            response = client.messages.create(
                model=settings.AI_MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                output_config={
                    "effort": settings.AI_EFFORT,
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
                },
            )
        except anthropic.APIError as error:
            # The SDK already retried network errors, 429s and 5xx; anything left is final.
            reply.error = f"API error: {error}"
            return reply
        reply.input_tokens += response.usage.input_tokens
        reply.output_tokens += response.usage.output_tokens
        reply.cost_usd = cost_usd(reply.input_tokens, reply.output_tokens)
        try:
            reply.data = parse(response)
            reply.error = ""
            return reply
        except InvalidReply as error:
            reply.error = f"Invalid reply: {error}"
    return reply


def parse(response):
    if response.stop_reason != "end_turn":
        raise InvalidReply(f"stopped with {response.stop_reason}")
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidReply(f"not JSON: {error}") from error
    validate(data)
    return data


def validate(data):
    """Checks the schema cannot express."""
    if not isinstance(data, dict) or set(data) != set(OUTPUT_SCHEMA["required"]):
        raise InvalidReply("wrong fields")
    if not isinstance(data["opus_score"], int) or not 0 <= data["opus_score"] <= 100:
        raise InvalidReply("opus_score must be an integer from 0 to 100")
    if data["direction"] not in DIRECTIONS:
        raise InvalidReply("unknown direction")
    reasons = data["reasons"]
    if not 3 <= len(reasons) <= 5 or not all(isinstance(r, str) and r.strip() for r in reasons):
        raise InvalidReply("reasons must be 3 to 5 short texts")
    stop = data["suggested_stop_loss_pct"]
    if not isinstance(stop, (int, float)) or not 0 < stop <= 50:
        raise InvalidReply("suggested_stop_loss_pct must be between 0 and 50")
