"""Image generation endpoint — uses gpt-image-1 via backend.tools.image_gen."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.api.deps import get_job_store
from backend.api.rate_limit import limiter
from backend.api.schemas import ImageRequest, ImageResponse
from backend.core.jobs import JobStore
from backend.core.logging import get_logger
from backend.core.paths import post_run_dir
from backend.core.pricing import image_cost
from backend.core.settings import get_settings
from backend.tools.image_gen import generate_image

router = APIRouter(prefix="/images", tags=["images"])
log = get_logger("api.images")


@router.post("", response_model=ImageResponse, status_code=201)
@limiter.limit(get_settings().rate_limit_images)
def post_image(
    request: Request,
    body: ImageRequest,
    store: JobStore = Depends(get_job_store),
) -> ImageResponse:
    job = store.get(body.job_id)
    if not job or job.kind != "posts" or not job.result:
        raise HTTPException(status_code=404, detail="post job not found or incomplete")

    run_id = job.result.get("run_id")
    if not run_id:
        raise HTTPException(status_code=400, detail="job has no run_id")

    settings = get_settings()
    quality = body.quality if body.quality in ("low", "medium", "high") else settings.image_default_quality

    try:
        path = generate_image(prompt=body.prompt, run_id=run_id, quality=quality)
    except Exception as exc:
        log.exception("image.generate.failed")
        raise HTTPException(status_code=502, detail=f"image generation failed: {exc}")

    image_id = path.stem  # "{run_id}_{NN}"

    # Update the job result so polling picks up the new path + cost
    new_result = dict(job.result)
    paths = list(new_result.get("image_paths", []))
    paths.append(str(path))
    new_result["image_paths"] = paths

    cost = dict(new_result.get("cost_breakdown") or {})
    img_block = dict(cost.get("image", {"calls": 0, "cost_usd": 0.0}))
    img_block["calls"] = int(img_block.get("calls", 0)) + 1
    per_image = image_cost(settings.image_model, settings.image_default_size, quality)
    img_block["cost_usd"] = round(float(img_block.get("cost_usd", 0.0)) + per_image, 6)
    cost["image"] = img_block

    crew_cost = float((cost.get("crew") or {}).get("cost_usd", 0.0))
    vd_cost = float((cost.get("visual_director") or {}).get("cost_usd", 0.0))
    cost["total_cost_usd"] = round(crew_cost + vd_cost + img_block["cost_usd"], 6)
    new_result["cost_breakdown"] = cost
    store.update(body.job_id, result=new_result)

    return ImageResponse(
        image_id=image_id,
        image_url=f"/api/v1/images/{image_id}",
        run_id=run_id,
    )


@router.get("/{image_id}")
def serve_image(image_id: str) -> FileResponse:
    """`image_id` has the form `<run_id>_<seq>` — use the trailing token to find the run dir."""
    if "_" not in image_id:
        raise HTTPException(status_code=400, detail="bad image_id")
    run_id = image_id.rsplit("_", 1)[0]
    candidate = post_run_dir(run_id) / f"{image_id}.png"
    if not candidate.exists():
        alt = next(post_run_dir(run_id).glob(f"*{image_id}*.png"), None)
        if alt:
            candidate = alt
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(str(candidate), media_type="image/png")
