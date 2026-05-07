# tests/api/test_health.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


def get_client():
    from api.main import app
    return TestClient(app)


def test_health_returns_200_with_all_keys_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        with get_client() as client:
            response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_has_request_id_header(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        with get_client() as client:
            response = client.get("/api/health")
    assert "x-request-id" in response.headers


def test_request_ids_are_unique(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        with get_client() as client:
            r1 = client.get("/api/health")
            r2 = client.get("/api/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_metrics_endpoint_returns_200(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    with (
        patch("api.routes.health._check_postgres", AsyncMock(return_value={"status": "ok"})),
        patch("api.routes.health._check_qdrant", AsyncMock(return_value={"status": "ok"})),
    ):
        with get_client() as client:
            client.get("/api/health")
            response = client.get("/metrics")
    assert response.status_code == 200
    assert b"http_requests_" in response.content
