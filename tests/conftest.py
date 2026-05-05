"""Shared test fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_outputs(tmp_path, monkeypatch):
    """Redirect outputs/ to a tmp dir so tests never pollute the real folder."""
    real_outputs = Path("outputs")
    fake = tmp_path / "outputs"
    fake.mkdir(parents=True, exist_ok=True)

    def _patched_outputs_dir() -> Path:
        return fake

    def _patched_jobs_dir() -> Path:
        p = fake / "jobs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _patched_history_path() -> Path:
        return fake / "history.jsonl"

    def _patched_post_run_dir(run_id: str) -> Path:
        p = fake / "posts" / run_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    from backend.core import paths as paths_mod

    monkeypatch.setattr(paths_mod, "outputs_dir", _patched_outputs_dir)
    monkeypatch.setattr(paths_mod, "jobs_dir", _patched_jobs_dir)
    monkeypatch.setattr(paths_mod, "history_path", _patched_history_path)
    monkeypatch.setattr(paths_mod, "post_run_dir", _patched_post_run_dir)

    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    # Reset cached job store between tests so fixtures don't leak.
    from backend.api import deps as deps_mod
    deps_mod.get_job_store.cache_clear()

    from backend.api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
