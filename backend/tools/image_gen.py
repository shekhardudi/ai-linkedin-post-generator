"""gpt-image-1 wrapper — saves a PNG to disk and returns its path.

Replaces the legacy DALL-E 3 helper. gpt-image-1 returns base64 directly,
so no second HTTP fetch is required.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from openai import OpenAI

from backend.core.logging import get_logger
from backend.core.paths import post_run_dir
from backend.core.settings import get_settings

log = get_logger("image_gen")


def generate_image(
    *,
    prompt: str,
    run_id: str,
    model: str | None = None,
    size: str | None = None,
    quality: str | None = None,
) -> Path:
    """Generate one image and save it under outputs/posts/{run_id}/{NN}.png.

    Returns the saved Path. Raises on API errors so callers can propagate.
    """
    s = get_settings()
    model = model or s.image_model
    size = size or s.image_default_size
    quality = quality or s.image_default_quality

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    log.info("image.generate.start", model=model, size=size, quality=quality, run_id=run_id)

    resp = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
    )

    datum = resp.data[0]
    if getattr(datum, "b64_json", None):
        img_bytes = base64.b64decode(datum.b64_json)
    elif getattr(datum, "url", None):
        # Some endpoints still return a URL — fetch it as a fallback path.
        import httpx

        img_bytes = httpx.get(datum.url, timeout=30.0).content
    else:
        raise RuntimeError("image response had neither b64_json nor url")

    out_dir = post_run_dir(run_id)
    seq = len(list(out_dir.glob("*.png"))) + 1
    out_path = out_dir / f"{run_id}_{seq:02d}.png"
    out_path.write_bytes(img_bytes)

    log.info("image.generate.done", path=str(out_path), run_id=run_id, seq=seq)
    return out_path
