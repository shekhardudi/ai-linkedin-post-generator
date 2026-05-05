"""Per-model pricing table (USD per 1M tokens unless noted).

Used by the cost tracker to convert token usage into dollars. Update when
providers publish new pricing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_m: float   # USD per 1M input tokens
    output_per_m: float  # USD per 1M output tokens


# Strings match LiteLLM-style identifiers used in agents.yaml.
TEXT_MODEL_PRICING: dict[str, ModelPricing] = {
    "openai/gpt-4o":            ModelPricing(5.00,  15.00),
    "openai/gpt-4o-mini":       ModelPricing(0.15,  0.60),
    "openai/gpt-5":             ModelPricing(8.00,  24.00),
    "openai/gpt-5-mini":        ModelPricing(0.50,  2.00),
    "anthropic/claude-sonnet-4-20250514":  ModelPricing(3.00, 15.00),
    "anthropic/claude-sonnet-4-6":         ModelPricing(3.00, 15.00),
    "anthropic/claude-opus-4-7":           ModelPricing(15.00, 75.00),
    "anthropic/claude-haiku-4-5-20251001": ModelPricing(1.00, 5.00),
}


# Image pricing is per-image at given size+quality. USD.
IMAGE_PRICING: dict[tuple[str, str, str], float] = {
    # (model, size, quality) -> USD per image
    ("dall-e-3",     "1024x1024", "standard"): 0.040,
    ("dall-e-3",     "1024x1024", "hd"):       0.080,
    ("gpt-image-1",  "1024x1024", "low"):      0.011,
    ("gpt-image-1",  "1024x1024", "medium"):   0.042,
    ("gpt-image-1",  "1024x1024", "high"):     0.167,
    ("gpt-image-1",  "1024x1536", "high"):     0.250,
    ("gpt-image-1",  "1536x1024", "high"):     0.250,
}


def text_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = TEXT_MODEL_PRICING.get(model)
    if not p:
        return 0.0
    return (input_tokens / 1_000_000) * p.input_per_m + (output_tokens / 1_000_000) * p.output_per_m


def image_cost(model: str, size: str = "1024x1024", quality: str = "standard") -> float:
    return IMAGE_PRICING.get((model, size, quality), 0.0)
