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
