# tests/api/test_anomalies.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from models.anomaly import AnomalyResult


def _make_anomaly(**kwargs) -> AnomalyResult:
    return AnomalyResult(
        log_id="log-001", score=0.4, is_anomaly=True, threshold=0.72, **kwargs
    )


@pytest.fixture
def test_app():
    from api.routes.anomalies import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.db_pool = MagicMock()
    return app


@pytest.mark.asyncio
async def test_get_anomalies_returns_200_with_results(test_app):
    anomaly = _make_anomaly()
    with patch("api.routes.anomalies.get_anomalies", return_value=([anomaly], 1)):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.get("/api/anomalies")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["results"][0]["log_id"] == "log-001"


@pytest.mark.asyncio
async def test_get_anomalies_passes_filters(test_app):
    with patch("api.routes.anomalies.get_anomalies", return_value=([], 0)) as mock_fn:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            await ac.get("/api/anomalies?reviewed=false&is_anomaly=true&limit=10&offset=5")

    kwargs = mock_fn.call_args.kwargs
    assert kwargs["reviewed"] is False
    assert kwargs["is_anomaly"] is True
    assert kwargs["limit"] == 10
    assert kwargs["offset"] == 5


@pytest.mark.asyncio
async def test_review_anomaly_returns_200(test_app):
    anomaly = _make_anomaly(reviewed=True)
    with patch("api.routes.anomalies.mark_anomaly_reviewed", return_value=anomaly), \
         patch("api.routes.anomalies.append_audit_log"):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/anomalies/{anomaly.id}/review")

    assert resp.status_code == 200
    assert resp.json()["anomaly"]["reviewed"] is True


@pytest.mark.asyncio
async def test_review_anomaly_returns_404_when_not_found(test_app):
    with patch("api.routes.anomalies.mark_anomaly_reviewed", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post("/api/anomalies/nonexistent/review")

    assert resp.status_code == 404
