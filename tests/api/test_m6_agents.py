from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from api.errors import http_exception_handler, set_request_id
from api.routes.agents import router as agents_router


@pytest.fixture
def test_app():
    app = FastAPI()

    @app.middleware("http")
    async def _set_rid(request, call_next):
        set_request_id(str(uuid.uuid4()))
        return await call_next(request)

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(agents_router, prefix="/api")
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
    assert body["request_id"] != ""
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
    assert "error" in body
    assert body["code"] == "http_501"
    assert body["request_id"] != ""
    assert "timestamp" in body
