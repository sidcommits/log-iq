# tests/api/test_correlate.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from intelligence.correlate import CorrelateResponse
from models.log_event import LogEvent, SeverityLevel


def _make_event(id="log-001", service="auth-service") -> LogEvent:
    return LogEvent(
        id=id,
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service=service,
        environment="production",
        message="error",
        source="loki",
        trace_id="trace-abc",
    )


@pytest.fixture
def test_app():
    from api.routes.correlate import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.db_pool = MagicMock()
    app.state.openai_client = MagicMock()
    app.state.qdrant_client = MagicMock()
    app.state.anthropic_client = MagicMock()
    app.state.config = {
        "rca": {"model": "claude-sonnet-4-20250514", "timeout_seconds": 30},
        "correlate": {"max_trace_logs": 200},
    }
    return app


@pytest.mark.asyncio
async def test_correlate_returns_200_with_logs_grouped(test_app):
    mock_response = CorrelateResponse(
        logs_by_service={"auth-service": [_make_event()]},
        rca_records=[],
        trace_summary=None,
    )

    with patch("api.routes.correlate.correlate_trace", return_value=mock_response):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.get("/api/correlate/trace-abc")

    assert resp.status_code == 200
    assert "auth-service" in resp.json()["logs_by_service"]
    assert resp.json()["trace_summary"] is None


@pytest.mark.asyncio
async def test_correlate_passes_fresh_analysis_flag(test_app):
    mock_response = CorrelateResponse(
        logs_by_service={"auth-service": [_make_event()]},
        rca_records=[],
        trace_summary="DB overload",
    )

    with patch("api.routes.correlate.correlate_trace", return_value=mock_response) as mock_fn:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.get("/api/correlate/trace-abc?fresh_analysis=true")

    assert resp.status_code == 200
    assert resp.json()["trace_summary"] == "DB overload"
    call_kwargs = mock_fn.call_args.kwargs
    assert call_kwargs["fresh_analysis"] is True


@pytest.mark.asyncio
async def test_correlate_returns_404_when_no_logs(test_app):
    with patch("api.routes.correlate.correlate_trace", side_effect=ValueError("no logs for trace_id")):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.get("/api/correlate/trace-missing")

    assert resp.status_code == 404
