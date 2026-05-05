"""Authority Crew endpoints — POST starts a 3-agent run, GET polls, PATCH saves edits."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from fastapi import Request

from backend.api.deps import get_job_runner, get_job_store
from backend.api.rate_limit import limiter
from backend.api.schemas import JobRef, PostJob, PostJobResult, PostRequest, PostUpdate
from backend.core.jobs import Job, JobRunner, JobStatus, JobStore
from backend.core.logging import get_logger
from backend.core.paths import new_run_id, post_run_dir
from backend.core.settings import get_settings
from backend.utils.cost_tracker import compute_post_cost
from backend.utils.history import append_run
from backend.utils.post_parser import extract_finalized_post

router = APIRouter(prefix="/posts", tags=["posts"])
log = get_logger("api.posts")


@router.post("", response_model=JobRef, status_code=202)
@limiter.limit(get_settings().rate_limit_posts)
async def start_post(
    request: Request,
    body: PostRequest,
    store: JobStore = Depends(get_job_store),
    runner: JobRunner = Depends(get_job_runner),
) -> JobRef:
    job = store.create("posts", body.model_dump())
    runner.schedule(job, _post_worker)
    return JobRef(job_id=job.id, status=job.status.value)


@router.get("/{job_id}", response_model=PostJob)
def get_post(job_id: str, store: JobStore = Depends(get_job_store)) -> PostJob:
    job = store.get(job_id)
    if not job or job.kind != "posts":
        raise HTTPException(status_code=404, detail="post job not found")
    return _to_schema(job)


@router.patch("/{job_id}", response_model=PostJob)
def update_post(
    job_id: str,
    body: PostUpdate,
    store: JobStore = Depends(get_job_store),
) -> PostJob:
    job = store.get(job_id)
    if not job or job.kind != "posts":
        raise HTTPException(status_code=404, detail="post job not found")
    if job.status != JobStatus.completed or not job.result:
        raise HTTPException(status_code=400, detail="post job is not completed")

    new_result = dict(job.result)
    new_result["post_draft"] = body.post_draft

    run_id = new_result.get("run_id")
    if run_id:
        out = post_run_dir(run_id) / "post_final.md"
        out.write_text(body.post_draft, encoding="utf-8")

    store.update(job_id, result=new_result)
    return _to_schema(store.get(job_id))  # type: ignore[arg-type]


def _to_schema(job: Job) -> PostJob:
    result = PostJobResult(**job.result) if job.result else None
    return PostJob(
        job_id=job.id,
        status=job.status.value,
        created_at=job.created_at,
        updated_at=job.updated_at,
        progress=job.progress,
        result=result,
        error=job.error,
    )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

async def _post_worker(job: Job, store: JobStore) -> dict[str, Any]:
    from crewai.events import (
        AgentReasoningCompletedEvent,
        ToolUsageFinishedEvent,
        ToolUsageStartedEvent,
        crewai_event_bus,
    )
    from crewai.events.types.agent_events import AgentExecutionStartedEvent

    from backend.post_generator.crew import AuthorityCrew
    from backend.post_generator.streaming import (
        EventEmitter,
        append_event,
        event_from_step,
        event_from_task,
        stage_event,
    )
    from backend.post_generator.visual_director import build_image_plan, extract_emotional_beats

    inputs = dict(job.inputs)
    audience = inputs.pop("audience", "engineering")
    today = date.today()
    inputs.setdefault("author_vibe", "calm, direct, and slightly skeptical")
    inputs["current_year"] = str(today.year)
    inputs["current_date"] = today.strftime("%B %d, %Y")
    inputs["current_date_minus_90"] = (today - timedelta(days=90)).strftime("%B %d, %Y")

    run_id = new_run_id()

    # Mutable closure state for streaming agent activity into progress.events
    stage = {"v": "research"}
    events: list[dict[str, Any]] = []
    task_seq = {"n": 0}
    stage_for_task = ["research", "writing", "critique"]

    def _flush_progress() -> None:
        store.update(
            job.id,
            progress={"stage": stage["v"], "run_id": run_id, "events": list(events)},
        )

    def _step_cb(step_output: Any) -> None:
        try:
            evt = event_from_step(step_output)
            append_event(events, evt)
            _flush_progress()
        except Exception:  # never let instrumentation kill the run
            log.exception("post.step_cb_failed")

    def _task_cb(task_output: Any) -> None:
        try:
            evt = event_from_task(task_output)
            append_event(events, evt)
            n = task_seq["n"] + 1
            task_seq["n"] = n
            if n < len(stage_for_task):
                stage["v"] = stage_for_task[n]
            _flush_progress()
        except Exception:
            log.exception("post.task_cb_failed")

    _flush_progress()

    loop = asyncio.get_running_loop()

    crew_obj = AuthorityCrew()
    crew_obj.step_callback = _step_cb
    crew_obj.task_callback = _task_cb
    built_crew = crew_obj.crew()

    emitter = EventEmitter(events, _flush_progress)

    def _run() -> Any:
        # Register handlers directly so the default CrewAI verbose printer
        # (EventListener singleton registered at import time) keeps working
        # in the terminal. scoped_handlers() wipes _sync_handlers entirely
        # on entry, which silences the printer for the duration of the run.
        crewai_event_bus.register_handler(ToolUsageStartedEvent, emitter.on_tool_started)
        crewai_event_bus.register_handler(ToolUsageFinishedEvent, emitter.on_tool_finished)
        crewai_event_bus.register_handler(AgentExecutionStartedEvent, emitter.on_agent_started)
        crewai_event_bus.register_handler(AgentReasoningCompletedEvent, emitter.on_reasoning_completed)
        try:
            return built_crew.kickoff(inputs=inputs)
        finally:
            try:
                crewai_event_bus.flush(timeout=5.0)
            except Exception:
                pass

    crew_output = await loop.run_in_executor(None, _run)
    raw = str(crew_output)

    # Crew is sequential — research is task 0, critic is the last task.
    research_md = ""
    try:
        tasks_output = getattr(crew_output, "tasks_output", None)
        if tasks_output:
            research_md = str(getattr(tasks_output[0], "raw", "") or tasks_output[0])
    except Exception:
        log.exception("post.research_extract_failed")

    post_draft, _legacy_image_prompt = extract_finalized_post(raw)
    beats = extract_emotional_beats(research_md)

    stage["v"] = "visual_director"
    append_event(
        events,
        stage_event("Visual Director", "Building image plan from finalized post + emotional beats…"),
    )
    _flush_progress()

    image_plan = await loop.run_in_executor(
        None,
        lambda: build_image_plan(
            post_text=post_draft,
            emotional_beats=beats,
            audience=audience,
            author_name=inputs.get("author_name", ""),
            author_title=inputs.get("author_title", ""),
        ),
    )
    vd_usage = image_plan.pop("_usage", {"input_tokens": 0, "output_tokens": 0})

    settings = get_settings()
    cost = compute_post_cost(
        crew_output=crew_output,
        crew_models=settings.crew_models(),
        visual_director_usage=vd_usage,
        visual_director_model=settings.visual_director_model,
        image_call_count=0,  # zero at post completion; /images calls add later
        image_model=settings.image_model,
        image_size=settings.image_default_size,
        image_quality=settings.image_default_quality,
    )

    out_dir = post_run_dir(run_id)
    (out_dir / "post_final.md").write_text(post_draft, encoding="utf-8")
    (out_dir / "raw_crew_output.md").write_text(raw, encoding="utf-8")
    if research_md:
        (out_dir / "fact_sheet.md").write_text(research_md, encoding="utf-8")
    (out_dir / "image_plan.json").write_text(json.dumps(image_plan, indent=2), encoding="utf-8")

    models = settings.model_card()
    # The Visual Director sometimes returns its own preferred image model — honour it.
    if image_plan.get("model"):
        models["image"] = image_plan["model"]

    append_run(
        {
            "run_id": run_id,
            "topic": inputs.get("topic", ""),
            "leader_angle": inputs.get("leader_angle", ""),
            "audience": audience,
            "post_path": str(Path("outputs") / "posts" / run_id / "post_final.md"),
            "image_paths": [],
            "cost_breakdown": cost.to_dict(),
            "models": models,
        }
    )

    return {
        "run_id": run_id,
        "post_draft": post_draft,
        "image_prompt": image_plan.get("image_prompt", ""),
        "image_plan": image_plan,
        "emotional_beats": beats,
        "raw_crew_output": raw,
        "cost_breakdown": cost.to_dict(),
    }
