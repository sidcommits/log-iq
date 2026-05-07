# api/errors.py
from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_request_id: ContextVar[str] = ContextVar("request_id", default="")

_PUBLIC_PATHS: frozenset[str] = frozenset({
    "/api/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
})


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    error_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error_msg,
            "code": f"http_{exc.status_code}",
            "request_id": _request_id.get(""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal server error",
            "code": "internal_error",
            "request_id": _request_id.get(""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def apply_auth(request: Request, config: dict) -> JSONResponse | None:
    """Returns 401 JSONResponse if auth fails, else None."""
    cfg = config.get("auth", {})
    if cfg.get("enabled") and request.url.path not in _PUBLIC_PATHS:
        key = request.headers.get("X-API-Key", "")
        if key != cfg.get("api_key", ""):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "invalid or missing API key",
                    "code": "unauthorized",
                    "request_id": _request_id.get(""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
    return None
