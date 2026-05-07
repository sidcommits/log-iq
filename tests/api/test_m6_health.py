# tests/api/test_m6_health.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
