"""Real cost tracking — driven by token usage from crewAI + Anthropic + image calls.

The legacy version re-tokenized text with tiktoken and applied GPT-4o pricing to
every model. That's wrong for Anthropic, wrong for image gen, and ignores cached
prompt tokens. This module instead reads what each provider actually reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.core.pricing import image_cost, text_cost


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: "TokenUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cached_prompt_tokens += other.cached_prompt_tokens


@dataclass
class CostBreakdown:
    crew_tokens: TokenUsage = field(default_factory=TokenUsage)
    crew_cost_usd: float = 0.0
    visual_director_tokens: TokenUsage = field(default_factory=TokenUsage)
    visual_director_cost_usd: float = 0.0
    image_calls: int = 0
    image_cost_usd: float = 0.0

    @property
    def total_cost_usd(self) -> float:
        return round(self.crew_cost_usd + self.visual_director_cost_usd + self.image_cost_usd, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "crew": {
                "prompt_tokens": self.crew_tokens.prompt_tokens,
                "completion_tokens": self.crew_tokens.completion_tokens,
                "total_tokens": self.crew_tokens.total_tokens,
                "cost_usd": round(self.crew_cost_usd, 6),
            },
            "visual_director": {
                "prompt_tokens": self.visual_director_tokens.prompt_tokens,
                "completion_tokens": self.visual_director_tokens.completion_tokens,
                "total_tokens": self.visual_director_tokens.total_tokens,
                "cost_usd": round(self.visual_director_cost_usd, 6),
            },
            "image": {
                "calls": self.image_calls,
                "cost_usd": round(self.image_cost_usd, 6),
            },
            "total_cost_usd": self.total_cost_usd,
        }


# ---------------------------------------------------------------------------
# Crew usage extraction — defensive against shape changes between crewAI versions
# ---------------------------------------------------------------------------

def _coerce_int(x: Any) -> int:
    try:
        return int(x or 0)
    except (TypeError, ValueError):
        return 0


def _crew_tokens(crew_output: Any) -> TokenUsage:
    """Best-effort read of `crew_output.token_usage` across crewAI versions."""
    usage = getattr(crew_output, "token_usage", None)
    if usage is None:
        return TokenUsage()

    if hasattr(usage, "prompt_tokens"):
        return TokenUsage(
            prompt_tokens=_coerce_int(getattr(usage, "prompt_tokens", 0)),
            completion_tokens=_coerce_int(getattr(usage, "completion_tokens", 0)),
            cached_prompt_tokens=_coerce_int(getattr(usage, "cached_prompt_tokens", 0)),
        )
    if isinstance(usage, dict):
        return TokenUsage(
            prompt_tokens=_coerce_int(usage.get("prompt_tokens")),
            completion_tokens=_coerce_int(usage.get("completion_tokens")),
            cached_prompt_tokens=_coerce_int(usage.get("cached_prompt_tokens")),
        )
    return TokenUsage()


def _crew_cost(usage: TokenUsage, model_mix: list[str]) -> float:
    """Apportion total tokens evenly across the participating models.

    crewAI's aggregate usage doesn't break tokens down by agent. Even split is
    close enough for a portfolio cost display; per-task usage was inconsistent
    across versions and not worth the complexity.
    """
    if not model_mix:
        return 0.0
    share_in = usage.prompt_tokens // max(len(model_mix), 1)
    share_out = usage.completion_tokens // max(len(model_mix), 1)
    return sum(text_cost(m, share_in, share_out) for m in model_mix)


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def compute_post_cost(
    *,
    crew_output: Any,
    crew_models: list[str],
    visual_director_usage: Optional[dict[str, int]] = None,
    visual_director_model: str = "anthropic/claude-sonnet-4-6",
    image_call_count: int = 0,
    image_model: str = "gpt-image-1",
    image_size: str = "1024x1024",
    image_quality: str = "high",
) -> CostBreakdown:
    """Build a single CostBreakdown from raw provider usage data."""
    crew_usage = _crew_tokens(crew_output)
    out = CostBreakdown(
        crew_tokens=crew_usage,
        crew_cost_usd=_crew_cost(crew_usage, crew_models),
    )

    if visual_director_usage:
        out.visual_director_tokens = TokenUsage(
            prompt_tokens=_coerce_int(visual_director_usage.get("input_tokens")),
            completion_tokens=_coerce_int(visual_director_usage.get("output_tokens")),
        )
        out.visual_director_cost_usd = text_cost(
            visual_director_model,
            out.visual_director_tokens.prompt_tokens,
            out.visual_director_tokens.completion_tokens,
        )

    out.image_calls = max(image_call_count, 0)
    out.image_cost_usd = out.image_calls * image_cost(image_model, image_size, image_quality)
    return out
