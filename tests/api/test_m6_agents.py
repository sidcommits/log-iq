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
