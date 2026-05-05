"""Filesystem path helpers — single source of truth for output locations."""

from datetime import datetime
from pathlib import Path


def repo_root() -> Path:
    """Repo root — backend/core/paths.py lives at <root>/backend/core/paths.py."""
    return Path(__file__).resolve().parent.parent.parent


def outputs_dir() -> Path:
    p = repo_root() / "outputs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def jobs_dir() -> Path:
    p = outputs_dir() / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def post_run_dir(run_id: str) -> Path:
    p = outputs_dir() / "posts" / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def history_path() -> Path:
    return outputs_dir() / "history.jsonl"


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
