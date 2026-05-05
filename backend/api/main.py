"""FastAPI app factory."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api.deps import get_job_store
from backend.api.errors import install_error_handlers
from backend.api.rate_limit import limiter
from backend.api.routes import health, history, images, posts, scout
from backend.core.jobs import JobRunner
from backend.core.logging import configure_logging, get_logger
from backend.core.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.log_level, pretty=settings.log_pretty)
    log = get_logger("api")

    store = get_job_store()
    runner = JobRunner(store, max_concurrent=settings.max_concurrent_post_jobs)
    app.state.job_store = store
    app.state.job_runner = runner

    log.info("api.startup", scout_backend=settings.scout_openai_model if settings.scout_use_openai else settings.ollama_model)
    try:
        yield
    finally:
        await runner.shutdown()
        cancelled = store.cancel_inflight()
        log.info("api.shutdown", cancelled_jobs=cancelled)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="LinkedIn Post Generator API",
        version="0.2.0",
        description="Pulse Scout + Authority Crew, exposed as async jobs.",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    install_error_handlers(app)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(scout.router, prefix="/api/v1")
    app.include_router(posts.router, prefix="/api/v1")
    app.include_router(images.router, prefix="/api/v1")
    app.include_router(history.router, prefix="/api/v1")

    return app


app = create_app()
