from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from intelligence.analyze import RCAContext
from models.log_event import LogEvent, SeverityLevel
from models.rca import RootCauseAnalysis
from models.task import ActionableTask, TaskPriority, TaskStatus


def _make_event(**kwargs) -> LogEvent:
    return LogEvent(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="db down",
        source="loki",
        **kwargs,
    )


def _make_rca(**kwargs) -> RootCauseAnalysis:
    return RootCauseAnalysis(
        log_id="log-001",
        summary="DB failure",
        root_cause="Pool exhausted",
        confidence=0.9,
        suggested_fixes=["Fix A"],
        **kwargs,
    )


def _make_task(rca_id: str) -> ActionableTask:
    return ActionableTask(
        rca_id=rca_id,
        log_id="log-001",
        title="Fix A",
        description="Fix A",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
    )


@pytest.fixture
def test_app():
    from api.routes.analyze import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.db_pool = MagicMock()
    app.state.openai_client = MagicMock()
    app.state.qdrant_client = MagicMock()
    app.state.anthropic_client = MagicMock()
    app.state.config = {
        "rca": {"semantic_neighbors": True, "max_semantic_k": 5, "trace_logs": True,
                "max_trace_logs": 20, "model": "claude-sonnet-4-20250514", "timeout_seconds": 30},
        "qdrant": {"collection": "log_events"},
    }
    return app


@pytest.mark.asyncio
async def test_analyze_returns_200_with_rca_and_tasks(test_app):
    rca = _make_rca()
    task = _make_task(rca.id)

    with patch("api.routes.analyze.build_rca_context", return_value=RCAContext(target=_make_event())), \
         patch("api.routes.analyze.run_rca", return_value=rca), \
         patch("api.routes.analyze.insert_rca"), \
         patch("api.routes.analyze.append_audit_log"), \
         patch("api.routes.analyze.create_tasks_from_rca", return_value=[task]):

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post("/api/analyze", json={"log_id": "log-001"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["rca"]["log_id"] == "log-001"
    assert len(body["tasks"]) == 1


@pytest.mark.asyncio
async def test_analyze_returns_404_when_log_not_found(test_app):
    with patch("api.routes.analyze.build_rca_context", side_effect=ValueError("log log-999 not found")):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post("/api/analyze", json={"log_id": "log-999"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyze_returns_502_on_llm_error(test_app):
    with patch("api.routes.analyze.build_rca_context", return_value=RCAContext(target=_make_event())), \
         patch("api.routes.analyze.run_rca", side_effect=RuntimeError("RCA timed out")):

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post("/api/analyze", json={"log_id": "log-001"})

    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_analyze_skips_task_creation_when_flag_false(test_app):
    rca = _make_rca()

    with patch("api.routes.analyze.build_rca_context", return_value=RCAContext(target=_make_event())), \
         patch("api.routes.analyze.run_rca", return_value=rca), \
         patch("api.routes.analyze.insert_rca"), \
         patch("api.routes.analyze.append_audit_log"), \
         patch("api.routes.analyze.create_tasks_from_rca") as mock_create:

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post("/api/analyze", json={"log_id": "log-001", "create_tasks": False})

    assert resp.status_code == 200
    mock_create.assert_not_called()
    assert resp.json()["tasks"] == []
