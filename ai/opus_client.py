"""The one place that calls the Anthropic API. Plain SDK calls, no agent framework."""

import json
from dataclasses import dataclass
from decimal import Decimal

import anthropic
from django.conf import settings

# US$ per million input / output tokens (Anthropic API, October 2026). Thinking tokens are
# billed and reported as output tokens. Haiku's prices are for prompts of 100K tokens or
# fewer (ours are ~2-3K); above that it costs 5x.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (Decimal("4.00"), Decimal("20.00")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
}
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
    model: str = ""


def model_label(model=None):
    """"claude-haiku-5-5" -> "Haiku 5.5", for the pages. Defaults to AI_MODEL."""
    parts = (model or settings.AI_MODEL).removeprefix("claude-").split("-")
    return f"{parts[0].capitalize()} {'.'.join(parts[1:])}".strip()


def make_client():
    # An empty key lets the SDK fall back to its other credential sources.
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)


def cost_usd(input_tokens, output_tokens, model=None):
    model = model or settings.AI_MODEL
    if model not in PRICES_PER_MTOK:
        # Never call a model whose cost cannot be logged.
        raise ValueError(f"No prices for {model}; add them to PRICES_PER_MTOK")
    input_price, output_price = PRICES_PER_MTOK[model]
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def ask(system_prompt, model_input, client=None, model=None):
    """Send the agent's data, get its verdict back as validated JSON.

    model: defaults to AI_MODEL. Tokens and cost add up over both attempts, since both are paid for.
    """
    model = model or settings.AI_MODEL
    cost_usd(0, 0, model)  # fails before any call if the model has no prices
    client = client or make_client()
    reply = OpusReply(data=None, model=model)
    user_message = json.dumps(model_input, indent=1, sort_keys=True)
    for _ in range(ATTEMPTS):
        try:
            response = client.messages.create(
                model=model,
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
        reply.cost_usd = cost_usd(reply.input_tokens, reply.output_tokens, model)
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
