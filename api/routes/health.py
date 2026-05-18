# api/routes/health.py
from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

_TIMEOUT = 5.0


async def _check_postgres(pool) -> dict:
    t0 = time.monotonic()
    try:
        async with asyncio.timeout(_TIMEOUT):
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return {"name": "postgresql", "status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        return {"name": "postgresql", "status": "error", "latency_ms": None, "detail": str(exc)}


async def _check_qdrant(qdrant_client, collection: str) -> dict:
    t0 = time.monotonic()
    try:
        async with asyncio.timeout(_TIMEOUT):
            await qdrant_client.get_collection(collection)
        return {"name": "qdrant", "status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        return {"name": "qdrant", "status": "error", "latency_ms": None, "detail": str(exc)}


def _check_env_key(name: str, env_var: str) -> dict:
    if os.environ.get(env_var):
        return {"name": name, "status": "ok", "latency_ms": None}
    return {"name": name, "status": "error", "latency_ms": None}


async def _fetch_metrics(pool) -> dict:
    try:
        async with pool.acquire() as conn:
            total_logs = await conn.fetchval("SELECT COUNT(*) FROM logs") or 0
            total_anomalies = await conn.fetchval("SELECT COUNT(*) FROM anomalies") or 0
            total_rcas = await conn.fetchval("SELECT COUNT(*) FROM rca") or 0
            pending_tasks = await conn.fetchval("SELECT COUNT(*) FROM tasks WHERE status = 'pending'") or 0
        return {
            "total_logs": total_logs,
            "total_anomalies": total_anomalies,
            "total_rcas": total_rcas,
            "pending_tasks": pending_tasks,
        }
    except Exception:
        return {"total_logs": 0, "total_anomalies": 0, "total_rcas": 0, "pending_tasks": 0}


async def _fetch_sync_sources(pool, config: dict) -> list:
    sources_cfg = config.get("sources", [])
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT source_name, last_synced_at FROM sync_cursors")
        cursors = {r["source_name"]: r["last_synced_at"] for r in rows}
    except Exception:
        cursors = {}

    result = []
    for src in sources_cfg:
        name = src.get("name", "unknown")
        last_synced = cursors.get(name)
        lag_ms = None
        if last_synced:
            import datetime
            lag_ms = round((datetime.datetime.now(datetime.timezone.utc) - last_synced).total_seconds() * 1000)
        result.append({
            "source_name": name,
            "mode": src.get("mode", "poll"),
            "last_synced_at": last_synced.isoformat() if last_synced else None,
            "lag_ms": lag_ms,
            "online": last_synced is not None,
        })
    return result


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    pool = request.app.state.db_pool
    qdrant = request.app.state.qdrant_client
    cfg = request.app.state.config
    collection = cfg["qdrant"].get("collection", "log_events")
    llm_provider = cfg.get("llm", {}).get("provider", "claude")

    # Determine which API key to check based on configured provider
    if llm_provider == "openrouter":
        llm_dep = _check_env_key("openrouter", "OPENROUTER_API_KEY")
    elif llm_provider == "openai":
        llm_dep = _check_env_key("openai_llm", "OPENAI_API_KEY")
    else:
        llm_dep = _check_env_key("claude", "ANTHROPIC_API_KEY")

    pg_result, qdrant_result, metrics, sync_sources = await asyncio.gather(
        _check_postgres(pool),
        _check_qdrant(qdrant, collection),
        _fetch_metrics(pool),
        _fetch_sync_sources(pool, cfg),
    )

    openai_embed_dep = _check_env_key("openai_embed", "OPENAI_API_KEY")

    dependencies = [pg_result, qdrant_result, openai_embed_dep, llm_dep]
    all_ok = all(d["status"] == "ok" for d in dependencies)
    status = "ok" if all_ok else "degraded"

    return JSONResponse(
        status_code=200,
        content={
            "status": status,
            "version": "1.0.0",
            "dependencies": dependencies,
            "sync_sources": sync_sources,
            "metrics": metrics,
        },
    )
