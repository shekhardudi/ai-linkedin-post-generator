"""Thin HTTP wrapper around the FastAPI backend.

The Streamlit UI imports nothing from `backend` — only this module.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
BASE = f"{API_URL}/api/v1"


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=timeout)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def health() -> dict[str, Any]:
    with _client() as c:
        r = c.get("/health")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------

def start_scout(modules: list[str], days: int) -> dict[str, Any]:
    with _client() as c:
        r = c.post("/scout", json={"modules": modules, "days": days})
        r.raise_for_status()
        return r.json()


def poll_scout(job_id: str) -> dict[str, Any]:
    with _client() as c:
        r = c.get(f"/scout/{job_id}")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Posts (Authority Crew)
# ---------------------------------------------------------------------------

def start_post(payload: dict[str, Any]) -> dict[str, Any]:
    with _client() as c:
        r = c.post("/posts", json=payload)
        r.raise_for_status()
        return r.json()


def poll_post(job_id: str) -> dict[str, Any]:
    with _client() as c:
        r = c.get(f"/posts/{job_id}")
        r.raise_for_status()
        return r.json()


def update_post(job_id: str, post_draft: str) -> dict[str, Any]:
    with _client() as c:
        r = c.patch(f"/posts/{job_id}", json={"post_draft": post_draft})
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def generate_image(job_id: str, prompt: str, quality: str = "medium") -> dict[str, Any]:
    # gpt-image-1 'high' commonly takes 60-90s; give the call generous headroom.
    with _client(timeout=240.0) as c:
        r = c.post("/images", json={"job_id": job_id, "prompt": prompt, "quality": quality})
        r.raise_for_status()
        return r.json()


def image_bytes(image_id: str) -> bytes:
    with _client() as c:
        r = c.get(f"/images/{image_id}")
        r.raise_for_status()
        return r.content


def image_url(image_id: str) -> str:
    return f"{BASE}/images/{image_id}"


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def list_history(limit: int = 50) -> list[dict[str, Any]]:
    with _client() as c:
        r = c.get("/history", params={"limit": limit})
        r.raise_for_status()
        return r.json()


def get_history(run_id: str) -> dict[str, Any]:
    with _client() as c:
        r = c.get(f"/history/{run_id}")
        r.raise_for_status()
        return r.json()
