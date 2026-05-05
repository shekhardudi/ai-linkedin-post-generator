"""Verify slowapi limits trip the right routes without breaking the rest."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_limiter_state():
    """slowapi keeps a process-global counter; reset it between tests."""
    from backend.api.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()


def test_health_is_not_rate_limited(client):
    for _ in range(20):
        r = client.get("/api/v1/health")
        assert r.status_code == 200


def test_posts_returns_429_when_burst_exceeds_limit(client):
    body = {
        "topic": "Mixture of Experts",
        "leader_angle": "",
        "author_name": "n",
        "author_title": "t",
        "author_location": "l",
    }
    statuses = []
    for _ in range(7):
        r = client.post("/api/v1/posts", json=body)
        statuses.append(r.status_code)
    # Limit is 5/minute — at least one of the last two requests must be 429.
    assert 429 in statuses, f"Expected a 429 in {statuses}"
