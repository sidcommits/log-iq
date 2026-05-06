# M6 — API Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the API layer with standardised error responses, `X-API-Key` auth, real health checks, missing routes (`/api/sources`, `/api/agents`), and full audit trail coverage.

**Architecture:** Extract error-handling helpers and auth logic into `api/errors.py` so they can be tested independently without importing the full app. New routes follow the existing pattern — minimal `FastAPI()` test apps per file, `patch()` to mock DB helpers, `AsyncClient` + `ASGITransport` for async assertions. `api/main.py` wires everything together last.

**Tech Stack:** FastAPI, pytest-asyncio, httpx, unittest.mock, contextvars, asyncio (Python 3.12)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `api/errors.py` | Create | `_request_id` ContextVar, error handlers, `apply_auth()`, `_PUBLIC_PATHS` |
| `api/routes/sources.py` | Create | `GET /api/sources` |
| `api/routes/agents.py` | Create | `GET /api/agents` + `POST /api/agents/trigger` (501 stubs) |
| `api/routes/health.py` | Modify | Real dependency checks via helper functions |
| `api/routes/search.py` | Modify | `search_executed` audit log after successful search |
| `api/main.py` | Modify | Import from `errors.py`, update middleware, add exception handlers, wire new routers |
| `tests/api/test_m6_errors.py` | Create | Error format + auth middleware tests |
| `tests/api/test_m6_sources.py` | Create | Sources route tests |
| `tests/api/test_m6_agents.py` | Create | Agents 501 stub tests |
| `tests/api/test_m6_health.py` | Create | Real health check tests (replaces old stubs in test_health.py) |
| `tests/api/test_m6_search_audit.py` | Create | Search audit log tests |

---

## Task 1: api/errors.py — ContextVar, error handlers, auth

**Files:**
- Create: `api/errors.py`
- Create: `tests/api/test_m6_errors.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_m6_errors.py
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient


def _make_error_app() -> FastAPI:
    from api.errors import (
        apply_auth,
        http_exception_handler,
        set_request_id,
        unhandled_exception_handler,
    )

    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.middleware("http")
    async def _set_rid(request, call_next):
        import uuid
        set_request_id(str(uuid.uuid4()))
        return await call_next(request)

    @app.get("/raise-404")
    async def _raise_404():
        raise HTTPException(status_code=404, detail="not found")

    @app.get("/raise-422")
    async def _raise_422():
        raise HTTPException(status_code=422, detail="validation failed")

    @app.get("/raise-500")
    async def _raise_500():
        raise RuntimeError("unexpected crash")

    @app.get("/api/protected")
    async def _protected():
        return {"ok": True}

    @app.get("/api/health")
    async def _health():
        return {"status": "healthy"}

    return app


@pytest.fixture
def error_app():
    return _make_error_app()


def _make_auth_app(config: dict) -> FastAPI:
    from api.errors import apply_auth

    app = FastAPI()

    @app.middleware("http")
    async def _auth(request, call_next):
        err = await apply_auth(request, config)
        if err:
            return err
        return await call_next(request)

    @app.get("/api/protected")
    async def _protected():
        return {"ok": True}

    @app.get("/api/health")
    async def _health():
        return {"status": "healthy"}

    return app


# --- Error format ---

@pytest.mark.asyncio
async def test_404_returns_standard_format(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.get("/raise-404")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not found"
    assert body["code"] == "http_404"
    assert "request_id" in body
    assert "timestamp" in body
    assert "detail" not in body


@pytest.mark.asyncio
async def test_422_returns_standard_format(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.get("/raise-422")
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation failed"
    assert body["code"] == "http_422"
    assert "request_id" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.get("/raise-500")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal server error"
    assert body["code"] == "internal_error"
    assert "request_id" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_request_id_in_error_body_is_nonempty(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.get("/raise-404")
    assert r.json()["request_id"] != ""


# --- Auth middleware ---

@pytest.mark.asyncio
async def test_auth_disabled_passes_any_request():
    app = _make_auth_app({"auth": {"enabled": False, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_missing_key_returns_401():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "unauthorized"
    assert "request_id" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_auth_enabled_wrong_key_returns_401():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_correct_key_passes():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected", headers={"X-API-Key": "secret"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_bypasses_health_endpoint():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/health")  # no key
    assert r.status_code == 200
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/sid/Desktop/Projects/log-IQ
pytest tests/api/test_m6_errors.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'api.errors'`

- [ ] **Step 3: Create api/errors.py**

```python
# api/errors.py
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_m6_errors.py -v
```

Expected: all green

- [ ] **Step 5: Commit**

```bash
git add api/errors.py tests/api/test_m6_errors.py
git commit -m "feat: api/errors.py — ContextVar, error handlers, apply_auth (TDD)"
```

---

## Task 2: api/routes/sources.py

**Files:**
- Create: `api/routes/sources.py`
- Create: `tests/api/test_m6_sources.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_m6_sources.py
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


_FAKE_CONFIG = {
    "sources": [
        {"name": "loki", "type": "loki", "url": "http://loki:3100", "mode": "stream"},
        {"name": "es", "type": "elasticsearch", "url": "http://es:9200", "mode": "poll"},
    ]
}


@pytest.fixture
def test_app():
    from api.routes.sources import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.config = _FAKE_CONFIG
    return app


@pytest.mark.asyncio
async def test_sources_returns_200(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        r = await ac.get("/api/sources")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_sources_returns_all_configured_sources(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        r = await ac.get("/api/sources")
    body = r.json()
    assert len(body["sources"]) == 2


@pytest.mark.asyncio
async def test_sources_shape(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        r = await ac.get("/api/sources")
    src = r.json()["sources"][0]
    assert src["name"] == "loki"
    assert src["type"] == "loki"
    assert src["url"] == "http://loki:3100"
    assert src["mode"] == "stream"


@pytest.mark.asyncio
async def test_sources_empty_when_no_sources_configured():
    from api.routes.sources import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.config = {"sources": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/sources")
    assert r.json()["sources"] == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/api/test_m6_sources.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'api.routes.sources'`

- [ ] **Step 3: Create api/routes/sources.py**

```python
# api/routes/sources.py
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class SourceInfo(BaseModel):
    name: str
    type: str
    url: str
    mode: str


class SourcesResponse(BaseModel):
    sources: list[SourceInfo]


@router.get("/sources", response_model=SourcesResponse)
async def list_sources(request: Request) -> SourcesResponse:
    raw = request.app.state.config.get("sources", [])
    return SourcesResponse(sources=[
        SourceInfo(
            name=s["name"],
            type=s["type"],
            url=s["url"],
            mode=s.get("mode", "poll"),
        )
        for s in raw
    ])
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_m6_sources.py -v
```

Expected: all green

- [ ] **Step 5: Commit**

```bash
git add api/routes/sources.py tests/api/test_m6_sources.py
git commit -m "feat: GET /api/sources route (TDD)"
```

---

## Task 3: api/routes/agents.py — 501 stubs

**Files:**
- Create: `api/routes/agents.py`
- Create: `tests/api/test_m6_agents.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_m6_agents.py
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def test_app():
    from api.routes.agents import router
    from api.errors import http_exception_handler
    from fastapi import HTTPException
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_get_agents_returns_501(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        r = await ac.get("/api/agents")
    assert r.status_code == 501


@pytest.mark.asyncio
async def test_get_agents_error_body(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        r = await ac.get("/api/agents")
    body = r.json()
    assert "error" in body
    assert body["code"] == "http_501"
    assert "request_id" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_post_agents_trigger_returns_501(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        r = await ac.post("/api/agents/trigger", json={})
    assert r.status_code == 501


@pytest.mark.asyncio
async def test_post_agents_trigger_error_body(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        r = await ac.post("/api/agents/trigger", json={})
    body = r.json()
    assert body["code"] == "http_501"
    assert "request_id" in body
    assert "timestamp" in body
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/api/test_m6_agents.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'api.routes.agents'`

- [ ] **Step 3: Create api/routes/agents.py**

```python
# api/routes/agents.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/agents")
async def list_agents() -> None:
    raise HTTPException(status_code=501, detail="agents API not available in v1.0")


@router.post("/agents/trigger")
async def trigger_agent() -> None:
    raise HTTPException(status_code=501, detail="agents API not available in v1.0")
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_m6_agents.py -v
```

Expected: all green

- [ ] **Step 5: Commit**

```bash
git add api/routes/agents.py tests/api/test_m6_agents.py
git commit -m "feat: GET /api/agents + POST /api/agents/trigger — 501 stubs (TDD)"
```

---

## Task 4: api/routes/health.py — real dependency checks

**Files:**
- Modify: `api/routes/health.py`
- Create: `tests/api/test_m6_health.py`

The new health route uses three private helper functions (`_check_postgres`, `_check_qdrant`, `_check_env_key`) so tests can patch them without needing a real DB.

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_m6_health.py
from __future__ import annotations

import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def test_app():
    from api.routes.health import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.db_pool = MagicMock()
    app.state.qdrant_client = AsyncMock()
    app.state.config = {"qdrant": {"collection": "logiq_logs"}}
    return app


_ALL_OK = {
    "api.routes.health._check_postgres": AsyncMock(return_value={"status": "ok"}),
    "api.routes.health._check_qdrant": AsyncMock(return_value={"status": "ok"}),
}

_PG_FAIL = {
    "api.routes.health._check_postgres": AsyncMock(
        return_value={"status": "error", "detail": "connection refused"}
    ),
    "api.routes.health._check_qdrant": AsyncMock(return_value={"status": "ok"}),
}


@pytest.mark.asyncio
async def test_health_returns_200_when_all_ok(test_app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            r = await ac.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_returns_503_when_postgres_fails(test_app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "error", "detail": "timeout"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            r = await ac.get("/api/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["dependencies"]["postgresql"]["status"] == "error"


@pytest.mark.asyncio
async def test_health_returns_503_when_qdrant_fails(test_app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "error", "detail": "refused"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            r = await ac.get("/api/health")
    assert r.status_code == 503
    assert r.json()["dependencies"]["qdrant"]["status"] == "error"


@pytest.mark.asyncio
async def test_health_returns_503_when_openai_key_missing(test_app, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            r = await ac.get("/api/health")
    assert r.status_code == 503
    assert r.json()["dependencies"]["openai"]["status"] == "error"


@pytest.mark.asyncio
async def test_health_response_shape_always_includes_all_deps(test_app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            r = await ac.get("/api/health")
    deps = r.json()["dependencies"]
    for key in ("postgresql", "qdrant", "openai", "claude"):
        assert key in deps
        assert "status" in deps[key]


@pytest.mark.asyncio
async def test_health_includes_version(test_app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            r = await ac.get("/api/health")
    assert r.json()["version"] == "0.1.0"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/api/test_m6_health.py -v 2>&1 | head -30
```

Expected: tests fail because health route still returns hardcoded stubs.

- [ ] **Step 3: Replace api/routes/health.py**

```python
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
```

- [ ] **Step 4: Run new tests — expect pass**

```bash
pytest tests/api/test_m6_health.py -v
```

Expected: all green

- [ ] **Step 5: Update existing test_health.py to match new behaviour**

The old `test_health_response_shape` asserts `"loki"` in deps and `"not_configured"` statuses — both now invalid. Replace those tests. Open `tests/api/test_health.py` and replace its content with:

```python
# tests/api/test_health.py
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


def get_client():
    from api.main import app
    return TestClient(app)


def test_health_returns_200_with_all_keys_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        response = get_client().get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_has_request_id_header(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        response = get_client().get("/api/health")
    assert "x-request-id" in response.headers


def test_request_ids_are_unique(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        client = get_client()
        r1 = client.get("/api/health")
        r2 = client.get("/api/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_metrics_endpoint_returns_200(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        client = get_client()
        client.get("/api/health")
        response = client.get("/metrics")
    assert response.status_code == 200
    assert b"http_requests_" in response.content
```

- [ ] **Step 6: Run all health tests — expect pass**

```bash
pytest tests/api/test_health.py tests/api/test_m6_health.py -v
```

Expected: all green

- [ ] **Step 7: Commit**

```bash
git add api/routes/health.py tests/api/test_m6_health.py tests/api/test_health.py
git commit -m "feat: /api/health — real dependency checks (TDD)"
```

---

## Task 5: api/routes/search.py — search_executed audit log

**Files:**
- Modify: `api/routes/search.py`
- Create: `tests/api/test_m6_search_audit.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_m6_search_audit.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from intelligence.search import SearchResponse, SearchResult
from models.log_event import LogEvent, SeverityLevel


def _make_event(**kwargs) -> LogEvent:
    defaults = dict(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="auth failure",
        source="loki",
    )
    return LogEvent(**{**defaults, **kwargs})


@pytest.fixture
def test_app():
    from api.routes.search import router as search_router
    app = FastAPI()
    app.include_router(search_router, prefix="/api")
    app.state.db_pool = MagicMock()
    app.state.openai_client = MagicMock()
    app.state.qdrant_client = MagicMock()
    return app


@pytest.mark.asyncio
async def test_search_calls_audit_log_on_success(test_app):
    event = _make_event()
    mock_response = SearchResponse(
        results=[SearchResult(log=event, score=0.90)],
        total=1,
        fallback_used=False,
    )
    with (
        patch("api.routes.search.semantic_search", return_value=mock_response),
        patch("api.routes.search.append_audit_log", new_callable=AsyncMock) as mock_audit,
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            await ac.post("/api/search", json={"query": "auth failure"})

    mock_audit.assert_awaited_once()
    call_args = mock_audit.call_args
    assert call_args.args[1] == "search_executed"
    payload = call_args.args[2]
    assert payload["query"] == "auth failure"
    assert payload["results"] == 1
    assert payload["fallback_used"] is False


@pytest.mark.asyncio
async def test_search_audit_log_not_called_on_empty_query(test_app):
    with patch("api.routes.search.append_audit_log", new_callable=AsyncMock) as mock_audit:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            await ac.post("/api/search", json={"query": "   "})
    mock_audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_audit_log_not_called_on_exception(test_app):
    with (
        patch("api.routes.search.semantic_search", side_effect=Exception("boom")),
        patch("api.routes.search.append_audit_log", new_callable=AsyncMock) as mock_audit,
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            await ac.post("/api/search", json={"query": "auth failure"})
    mock_audit.assert_not_awaited()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/api/test_m6_search_audit.py -v 2>&1 | head -20
```

Expected: `AssertionError: Expected call not found` — `append_audit_log` is never called.

- [ ] **Step 3: Update api/routes/search.py**

Replace the file content with:

```python
# api/routes/search.py
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log
from intelligence.search import SearchFilters, SearchResponse, semantic_search

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    filters: SearchFilters | None = None
    limit: int = 20


@router.post("/search", response_model=SearchResponse)
async def search_logs(body: SearchRequest, request: Request) -> SearchResponse:
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="query must not be empty")
    try:
        result = await asyncio.wait_for(
            semantic_search(
                query=body.query,
                filters=body.filters,
                limit=min(body.limit, 100),
                pool=request.app.state.db_pool,
                openai_client=request.app.state.openai_client,
                qdrant_client=request.app.state.qdrant_client,
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="search timed out")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    await append_audit_log(
        request.app.state.db_pool,
        "search_executed",
        {
            "query": body.query,
            "results": len(result.results),
            "fallback_used": result.fallback_used,
        },
    )
    return result
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_m6_search_audit.py tests/api/test_search.py -v
```

Expected: all green (new audit tests pass; existing search tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add api/routes/search.py tests/api/test_m6_search_audit.py
git commit -m "feat: search_executed audit log on successful search (TDD)"
```

---

## Task 6: Wire everything into api/main.py

**Files:**
- Modify: `api/main.py`

This task has no new test file — the integration is validated by running the full existing test suite.

- [ ] **Step 1: Replace api/main.py**

```python
# api/main.py
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from openai import AsyncOpenAI
from prometheus_fastapi_instrumentator import Instrumentator

from api.errors import (
    apply_auth,
    http_exception_handler,
    set_request_id,
    unhandled_exception_handler,
)
from api.routes.agents import router as agents_router
from api.routes.analyze import router as analyze_router
from api.routes.anomalies import router as anomalies_router
from api.routes.correlate import router as correlate_router
from api.routes.health import router as health_router
from api.routes.search import router as search_router
from api.routes.sources import router as sources_router
from api.routes.tasks import router as tasks_router
from db.postgres import init_pool
from db.qdrant import ensure_collection, init_qdrant
from ingestion.pipeline import IngestionWorker
from sync.engine import SyncEngine

_config: dict = yaml.safe_load(
    (Path(__file__).parent.parent / "config.yaml").read_text()
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = _config
    app.state.db_pool = await init_pool(dsn=_config["database"]["url"])

    qdrant_cfg = _config["qdrant"]
    app.state.qdrant_client = await init_qdrant(
        host=qdrant_cfg["host"], port=qdrant_cfg["port"]
    )
    await ensure_collection(app.state.qdrant_client, qdrant_cfg.get("collection", "log_events"))

    app.state.openai_client = AsyncOpenAI()
    app.state.anthropic_client = AsyncAnthropic()

    engine = SyncEngine(config=_config, pool=app.state.db_pool)
    await engine.start()

    ingestion_worker = IngestionWorker(
        pool=app.state.db_pool,
        openai_client=app.state.openai_client,
        qdrant_client=app.state.qdrant_client,
        batch_size=_config["ingestion"].get("batch_size", 100),
        collection=qdrant_cfg.get("collection", "log_events"),
        anomaly_config=_config.get("anomaly", {}),
    )
    await ingestion_worker.start()

    yield

    await ingestion_worker.stop()
    await engine.stop()
    await app.state.db_pool.close()


app = FastAPI(title="LogIQ", version="0.1.0", lifespan=lifespan)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Middleware ordering: Starlette prepends each add_middleware call, so the LAST
# registered middleware is the OUTERMOST (executes first). We want:
#   CORSMiddleware (outermost) → add_request_id → auth_middleware → route
# So: auth registered 1st (inner), add_request_id 2nd (outer), CORS 3rd (outermost).

@app.middleware("http")
async def auth_middleware(request: Request, call_next) -> Response:
    err = await apply_auth(request, _config)
    if err:
        return err
    return await call_next(request)


@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    rid = str(uuid.uuid4())
    set_request_id(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(health_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(correlate_router, prefix="/api")
app.include_router(anomalies_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/api/ -v
```

Expected: all green. If `test_health.py` tests fail due to env vars, confirm the monkeypatching in step 5 of Task 4 was applied.

- [ ] **Step 3: Commit**

```bash
git add api/main.py
git commit -m "feat: wire M6 — error handlers, auth middleware, sources + agents routers into main (TDD)"
```

---

## Task 7: Full suite smoke check

- [ ] **Step 1: Run entire test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -40
```

Expected: all green, no regressions across adapters, db, ingestion, intelligence, or api tests.

- [ ] **Step 2: Verify all required routes exist**

```bash
python -c "
from api.main import app
routes = {r.path for r in app.routes}
required = {
    '/api/health', '/api/search', '/api/analyze',
    '/api/correlate/{trace_id}', '/api/anomalies',
    '/api/anomalies/{anomaly_id}/review', '/api/tasks',
    '/api/tasks/{task_id}/approve', '/api/tasks/{task_id}/dismiss',
    '/api/sources', '/api/agents', '/api/agents/trigger', '/metrics',
}
missing = required - routes
print('MISSING:', missing or 'none')
print('ALL ROUTES:', sorted(routes))
"
```

Expected: `MISSING: none`

- [ ] **Step 3: Final commit if needed**

If no uncommitted changes remain, skip. Otherwise:

```bash
git add -A
git commit -m "chore: M6 API Polish complete"
```
