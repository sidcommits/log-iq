# tests/api/test_tasks.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from models.task import ActionableTask, TaskPriority, TaskStatus


def _make_task(**kwargs) -> ActionableTask:
    defaults: dict = dict(
        rca_id="rca-001",
        log_id="log-001",
        title="Fix pool",
        description="Increase pool size",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
    )
    return ActionableTask(**{**defaults, **kwargs})


@pytest.fixture
def test_app():
    from api.routes.tasks import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.db_pool = MagicMock()
    return app


@pytest.mark.asyncio
async def test_get_tasks_returns_200(test_app):
    task = _make_task()
    with patch("api.routes.tasks.get_tasks", return_value=([task], 1)):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.get("/api/tasks")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_tasks_passes_filters(test_app):
    with patch("api.routes.tasks.get_tasks", return_value=([], 0)) as mock_fn:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            await ac.get("/api/tasks?status=pending&priority=high&limit=10&offset=5")

    kwargs = mock_fn.call_args.kwargs
    assert kwargs["status"] == "pending"
    assert kwargs["priority"] == "high"


@pytest.mark.asyncio
async def test_approve_task_returns_200_for_pending_task(test_app):
    pending = _make_task(status=TaskStatus.PENDING)
    approved = _make_task(status=TaskStatus.APPROVED)

    with patch("api.routes.tasks.get_task_by_id", return_value=pending), \
         patch("api.routes.tasks.update_task_status", return_value=approved), \
         patch("api.routes.tasks.append_audit_log"):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{pending.id}/approve")

    assert resp.status_code == 200
    assert resp.json()["task"]["status"] == "approved"


@pytest.mark.asyncio
async def test_approve_task_returns_404_when_not_found(test_app):
    with patch("api.routes.tasks.get_task_by_id", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post("/api/tasks/nonexistent/approve")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_task_returns_409_when_already_approved(test_app):
    approved = _make_task(status=TaskStatus.APPROVED)
    with patch("api.routes.tasks.get_task_by_id", return_value=approved):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{approved.id}/approve")

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_dismiss_task_returns_200(test_app):
    pending = _make_task(status=TaskStatus.PENDING)
    dismissed = _make_task(status=TaskStatus.DISMISSED)
    with patch("api.routes.tasks.get_task_by_id", return_value=pending), \
         patch("api.routes.tasks.update_task_status", return_value=dismissed), \
         patch("api.routes.tasks.append_audit_log"):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{pending.id}/dismiss")

    assert resp.status_code == 200
    assert resp.json()["task"]["status"] == "dismissed"


@pytest.mark.asyncio
async def test_dismiss_task_returns_409_when_resolved(test_app):
    resolved = _make_task(status=TaskStatus.RESOLVED)
    with patch("api.routes.tasks.get_task_by_id", return_value=resolved):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{resolved.id}/dismiss")

    assert resp.status_code == 409
