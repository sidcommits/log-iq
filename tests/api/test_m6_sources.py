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
