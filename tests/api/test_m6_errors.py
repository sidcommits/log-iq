# tests/api/test_m6_errors.py
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel


class _ValidationBody(BaseModel):
    required_field: str


def _make_error_app() -> FastAPI:
    from fastapi.exceptions import RequestValidationError

    from api.errors import (
        http_exception_handler,
        request_validation_exception_handler,
        set_request_id,
        unhandled_exception_handler,
    )

    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.middleware("http")
    async def _set_rid(request, call_next):
        set_request_id(str(uuid.uuid4()))
        return await call_next(request)

    @app.get("/raise-404")
    async def _raise_404():
        raise HTTPException(status_code=404, detail="not found")

    @app.get("/raise-422")
    async def _raise_422():
        raise HTTPException(status_code=422, detail="validation failed")

    @app.get("/raise-500")
    async def _raise_500():
        raise RuntimeError("unexpected crash")

    @app.get("/api/protected")
    async def _protected():
        return {"ok": True}

    @app.get("/api/health")
    async def _health():
        return {"status": "healthy"}

    @app.post("/raise-validation")
    async def _raise_validation(body: _ValidationBody):
        return {"ok": True}

    return app


@pytest.fixture
def error_app():
    return _make_error_app()


def _make_auth_app(config: dict) -> FastAPI:
    from api.errors import apply_auth

    app = FastAPI()

    @app.middleware("http")
    async def _auth(request, call_next):
        err = await apply_auth(request, config)
        if err:
            return err
        return await call_next(request)

    @app.get("/api/protected")
    async def _protected():
        return {"ok": True}

    @app.get("/api/health")
    async def _health():
        return {"status": "healthy"}

    return app


# --- Error format ---

@pytest.mark.asyncio
async def test_404_returns_standard_format(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.get("/raise-404")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not found"
    assert body["code"] == "http_404"
    assert "request_id" in body
    assert "timestamp" in body
    assert "detail" not in body


@pytest.mark.asyncio
async def test_422_returns_standard_format(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.get("/raise-422")
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation failed"
    assert body["code"] == "http_422"
    assert "request_id" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500(error_app):
    # raise_app_exceptions=False: ServerErrorMiddleware calls our handler then re-raises;
    # ASGITransport must not propagate that re-raise so we can assert on the 500 response.
    async with AsyncClient(transport=ASGITransport(app=error_app, raise_app_exceptions=False), base_url="http://test") as ac:
        r = await ac.get("/raise-500")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal server error"
    assert body["code"] == "internal_error"
    assert "request_id" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_request_id_in_error_body_is_nonempty(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.get("/raise-404")
    assert r.json()["request_id"] != ""


# --- Auth middleware ---

@pytest.mark.asyncio
async def test_auth_disabled_passes_any_request():
    app = _make_auth_app({"auth": {"enabled": False, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_missing_key_returns_401():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "unauthorized"
    assert "request_id" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_auth_enabled_wrong_key_returns_401():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_correct_key_passes():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected", headers={"X-API-Key": "secret"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_bypasses_health_endpoint():
    app = _make_auth_app({"auth": {"enabled": True, "api_key": "secret"}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/health")  # no key
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_request_validation_error_returns_standard_format(error_app):
    async with AsyncClient(transport=ASGITransport(app=error_app), base_url="http://test") as ac:
        r = await ac.post("/raise-validation", json={})  # missing required_field
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "request validation failed"
    assert body["code"] == "http_422"
    assert "request_id" in body
    assert "timestamp" in body
    assert "detail" not in body
