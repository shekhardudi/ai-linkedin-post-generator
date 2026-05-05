"""Visual Director — turns a finalized post into a structured image plan.

Runs after the crew completes. One LLM call (Claude Sonnet 4.6) with the
image_prompt_builder template. Returns a dict with the plan AND the final
gpt-image-1 prompt string.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from anthropic import Anthropic

from backend.core.logging import get_logger
from backend.core.settings import get_settings
from backend.prompts import load as load_prompt

log = get_logger("visual_director")


def _sdk_model_id(model_string: str) -> str:
    """Strip the LiteLLM-style provider prefix when calling the Anthropic SDK directly."""
    return model_string.split("/", 1)[-1]


def extract_emotional_beats(fact_sheet_md: str) -> list[str]:
    """Pull the 3 short phrases from the Fact Sheet's `## Emotional Beats` section."""
    if not fact_sheet_md:
        return []
    m = re.search(
        r"##\s*Emotional Beats\s*\n(.*?)(?=\n##\s|\Z)",
        fact_sheet_md,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return []
    body = m.group(1).strip()
    beats: list[str] = []
    for line in body.splitlines():
        line = line.strip().lstrip("-•* ").strip()
        if line:
            beats.append(line)
    return beats[:3]


def build_image_plan(
    *,
    post_text: str,
    emotional_beats: list[str],
    audience: str,
    author_name: str,
    author_title: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Return the structured image plan + the final gpt-image-1 prompt.

    Falls back to a hand-built plan if the LLM call or JSON parse fails — the
    pipeline should never wedge on a flaky visual step.
    """
    template = load_prompt("image_prompt_builder")
    beats_str = "\n".join(f"- {b}" for b in emotional_beats) if emotional_beats else "- (none provided)"
    rendered = template.format(
        audience=audience,
        author_name=author_name,
        author_title=author_title,
        emotional_beats=beats_str,
        post_text=post_text,
    )

    settings = get_settings()
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("visual_director.no_api_key — using fallback plan")
        plan = _fallback_plan(post_text, audience)
        plan["model"] = settings.image_model
        return plan

    try:
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=_sdk_model_id(settings.visual_director_model),
            max_tokens=settings.visual_director_max_tokens,
            temperature=settings.visual_director_temperature,
            messages=[{"role": "user", "content": rendered}],
        )
        text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        plan = _parse_json_block(text)
        usage = {
            "input_tokens": int(getattr(msg.usage, "input_tokens", 0)),
            "output_tokens": int(getattr(msg.usage, "output_tokens", 0)),
        }
    except Exception as exc:
        log.exception("visual_director.failed", error=str(exc))
        plan = _fallback_plan(post_text, audience)
        plan["_usage"] = {"input_tokens": 0, "output_tokens": 0}
        return plan

    if not plan or not plan.get("image_prompt"):
        plan = _fallback_plan(post_text, audience)
        plan["_usage"] = usage
        plan["model"] = settings.image_model
        return plan

    plan.setdefault("model", settings.image_model)
    plan["_usage"] = usage
    return plan


def _parse_json_block(text: str) -> dict[str, Any] | None:
    """Strict-then-lenient JSON parser for LLM output that may wrap JSON in prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def _fallback_plan(post_text: str, audience: str) -> dict[str, Any]:
    scene = (
        "An engineer at a desk lit by a single monitor, hands paused over a keyboard, "
        "an empty coffee mug catching the screen's glow"
        if audience == "engineering"
        else
        "A founder reading a printed report at a long boardroom table, "
        "morning light cutting across the page"
    )
    prompt = (
        f"{scene}. Photographic, shot on 35mm, natural light, shallow depth of field, "
        f"editorial composition, no text overlay, no AI imagery, no glowing screens, "
        f"no robots, no circuitry. Muted colour palette. The mood is honest reassessment."
    )
    return {
        "style": "A",
        "scene": scene,
        "emotion": "honest reassessment",
        "composition": "35mm, natural light, shallow depth of field",
        "text_overlay": None,
        "accent_color": "muted daylight",
        "image_prompt": prompt,
        "model": get_settings().image_model,
    }
