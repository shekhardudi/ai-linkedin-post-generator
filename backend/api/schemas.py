"""Pydantic request/response schemas for the FastAPI layer."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    version: str
    keys_present: dict[str, bool]
    scout_backend: str
    ollama_reachable: Optional[bool] = None


class JobRef(BaseModel):
    job_id: str
    status: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------

class ScoutRequest(BaseModel):
    modules: list[str] = Field(..., min_length=1)
    days: int = Field(7, ge=0, le=730)


class ScoutJobResult(BaseModel):
    report_md: str
    modules: list[str]
    days: int
    cost_breakdown: Optional[dict[str, Any]] = None


class ScoutJob(BaseModel):
    job_id: str
    kind: str = "scout"
    status: str
    created_at: str
    updated_at: str
    progress: dict[str, Any] = Field(default_factory=dict)
    result: Optional[ScoutJobResult] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

class PostRequest(BaseModel):
    topic: str = Field(..., min_length=2)
    leader_angle: str = ""
    author_name: str
    author_title: str
    author_location: str
    author_vibe: str = ""
    audience: str = Field("engineering", description="'engineering' or 'business'")


class PostJobResult(BaseModel):
    run_id: str
    post_draft: str
    image_prompt: str = ""
    image_plan: Optional[dict[str, Any]] = None
    emotional_beats: list[str] = Field(default_factory=list)
    raw_crew_output: str = ""
    cost_breakdown: Optional[dict[str, Any]] = None


class PostJob(BaseModel):
    job_id: str
    kind: str = "posts"
    status: str
    created_at: str
    updated_at: str
    progress: dict[str, Any] = Field(default_factory=dict)
    result: Optional[PostJobResult] = None
    error: Optional[str] = None


class PostUpdate(BaseModel):
    post_draft: str


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class ImageRequest(BaseModel):
    job_id: str
    prompt: str = Field(..., min_length=10)
    quality: str = Field("", description="'low' | 'medium' | 'high'; blank uses Settings.image_default_quality")


class ImageResponse(BaseModel):
    image_id: str
    image_url: str  # /api/v1/images/{image_id}
    run_id: str


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class HistoryRow(BaseModel):
    run_id: str
    created_at: str
    topic: str
    leader_angle: str = ""
    audience: str = "engineering"
    post_path: Optional[str] = None
    image_paths: list[str] = Field(default_factory=list)
    cost_breakdown: Optional[dict[str, Any]] = None
    models: Optional[dict[str, str]] = None
