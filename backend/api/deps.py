"""FastAPI dependency providers — settings, job store, job runner."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Request

from backend.core.jobs import JobRunner, JobStore
from backend.core.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_job_store() -> JobStore:
    return JobStore()


def get_job_runner(request: Request) -> JobRunner:
    """The runner is created in the API lifespan and stored on app.state."""
    return request.app.state.job_runner


def get_app_settings() -> Settings:
    return get_settings()
