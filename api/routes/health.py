# api/routes/health.py
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

_TIMEOUT = 5.0


async def _check_postgres(pool) -> dict:
    try:
        async with asyncio.timeout(_TIMEOUT):
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_qdrant(qdrant_client, collection: str) -> dict:
    try:
        async with asyncio.timeout(_TIMEOUT):
            await qdrant_client.get_collection(collection)
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_env_key(env_var: str) -> dict:
    if os.environ.get(env_var):
        return {"status": "ok"}
    return {"status": "error", "detail": f"{env_var} not set"}


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    pool = request.app.state.db_pool
    qdrant = request.app.state.qdrant_client
    collection = request.app.state.config["qdrant"].get("collection", "log_events")

    pg_result, qdrant_result = await asyncio.gather(
        _check_postgres(pool),
        _check_qdrant(qdrant, collection),
    )
    openai_result = _check_env_key("OPENAI_API_KEY")
    claude_result = _check_env_key("ANTHROPIC_API_KEY")

    dependencies = {
        "postgresql": pg_result,
        "qdrant": qdrant_result,
        "openai": openai_result,
        "claude": claude_result,
    }
    all_ok = all(v["status"] == "ok" for v in dependencies.values())
    status = "healthy" if all_ok else "degraded"
    http_status = 200 if all_ok else 503

    return JSONResponse(
        status_code=http_status,
        content={"status": status, "version": "0.1.0", "dependencies": dependencies},
    )
