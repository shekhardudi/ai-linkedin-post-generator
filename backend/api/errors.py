"""Single exception → JSON error body mapper for the API."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.logging import get_logger

log = get_logger("api.errors")


class EngineError(Exception):
    """Raised by engine layer when something inside the AI pipeline fails."""


def _body(code: str, message: str, request_id: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(EngineError)
    async def _engine_error(request: Request, exc: EngineError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        log.error("engine.error", error=str(exc), request_id=rid)
        return JSONResponse(status_code=500, content=_body("engine_error", str(exc), rid))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", str(exc.errors()), rid),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", None) or uuid.uuid4().hex
        log.exception("unhandled.error", request_id=rid)
        return JSONResponse(
            status_code=500,
            content=_body("internal_error", "Something went wrong.", rid),
        )
