"""Health check — verifies key presence + Scout backend reachability."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from backend.api.deps import get_app_settings
from backend.api.schemas import HealthResponse
from backend.core.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    keys = {
        "openai": bool(settings.openai_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "tavily": bool(settings.tavily_api_key),
    }
    if settings.scout_use_openai:
        backend = f"openai/{settings.scout_openai_model}"
        ollama_ok = None
    else:
        backend = f"ollama/{settings.ollama_model}"
        ollama_ok = _ping_ollama(settings.ollama_base_url)

    return HealthResponse(
        status="ok",
        version="0.2.0",
        keys_present=keys,
        scout_backend=backend,
        ollama_reachable=ollama_ok,
    )


def _ping_ollama(base_url: str) -> bool:
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False
