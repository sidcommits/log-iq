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
async def test_search_returns_200_with_results(test_app):
    event = _make_event()
    mock_response = SearchResponse(
        results=[SearchResult(log=event, score=0.90)],
        total=1,
        fallback_used=False,
    )

    with patch("api.routes.search.semantic_search", return_value=mock_response):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/search", json={"query": "auth failure"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["fallback_used"] is False
    assert body["results"][0]["score"] == 0.90


@pytest.mark.asyncio
async def test_search_returns_422_for_whitespace_only_query(test_app):
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        resp = await ac.post("/api/search", json={"query": "   "})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_503_on_search_exception(test_app):
    with patch(
        "api.routes.search.semantic_search", side_effect=Exception("OpenAI down")
    ):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/search", json={"query": "auth failure"})

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_search_includes_fallback_flag_in_response(test_app):
    event = _make_event()
    mock_response = SearchResponse(
        results=[SearchResult(log=event, score=0.0)],
        total=1,
        fallback_used=True,
    )

    with patch("api.routes.search.semantic_search", return_value=mock_response):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            resp = await ac.post("/api/search", json={"query": "auth failure"})

    assert resp.json()["fallback_used"] is True
