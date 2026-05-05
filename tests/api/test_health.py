import pytest
from fastapi.testclient import TestClient


def get_client():
    from api.main import app
    return TestClient(app)


def test_health_returns_200():
    response = get_client().get("/api/health")
    assert response.status_code == 200


def test_health_response_shape():
    response = get_client().get("/api/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"
    deps = data["dependencies"]
    for key in ("loki", "qdrant", "postgresql", "openai", "claude"):
        assert key in deps
        assert deps[key]["status"] == "not_configured"


def test_health_has_request_id_header():
    response = get_client().get("/api/health")
    assert "x-request-id" in response.headers


def test_request_ids_are_unique():
    client = get_client()
    r1 = client.get("/api/health")
    r2 = client.get("/api/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_metrics_endpoint_returns_200():
    client = get_client()
    client.get("/api/health")  # generate at least one metric
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"http_requests_" in response.content
