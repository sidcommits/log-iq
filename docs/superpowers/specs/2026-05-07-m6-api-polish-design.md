# M6 — API Polish Design

**Date:** 2026-05-07  
**Milestone:** M6 — API Polish (Day 8)  
**Scope:** All FastAPI routes, Prometheus metrics, error handling, audit trail

---

## 1. Context

M6 completes the backend API layer. Core routes (search, analyze, correlate, anomalies, tasks) were built in M3–M5. M6 adds the missing routes, enforces a standard error format, implements real health checks, and fills the remaining audit trail gaps.

**Already in place (not re-implemented):**
- `/metrics` Prometheus via `prometheus-fastapi-instrumentator`
- Request ID added to response header via middleware
- `audit_log` table + `append_audit_log()` helper
- Audit calls: `rca_created`, `task_created`, `task_approved`, `task_dismissed`, `anomaly_reviewed`
- Core routes: search, analyze, correlate, anomalies, tasks, health (stub)

---

## 2. Architecture

### 2.1 Error Handling

**Approach:** Global exception handlers registered on the FastAPI app in `main.py`.

A `contextvars.ContextVar[str]` called `_request_id` is set per-request in the existing `add_request_id` middleware. Both exception handlers read from it to populate `request_id` in error bodies.

Standard error response shape (all status codes):
```json
{
  "error": "<human-readable message>",
  "code": "<machine code>",
  "request_id": "<uuid>",
  "timestamp": "<ISO8601 UTC>"
}
```

Two handlers:
- `@app.exception_handler(HTTPException)` → `code: "http_{status_code}"`, `error: exc.detail`
- `@app.exception_handler(Exception)` → `code: "internal_error"`, `error: "internal server error"`, status 500

Zero changes to existing routes — they continue raising `HTTPException` as-is.

### 2.2 Auth Middleware

New HTTP middleware added to `main.py`. Runs after request ID is set.

When `config.auth.enabled = true`:
- Reads `X-API-Key` header
- Compares against `config.auth.api_key` (resolved from `${LOGIQ_API_KEY}` env var)
- Returns `401` in standard error format if missing or wrong

Public paths that bypass auth (always accessible):
```
/api/health
/metrics
/docs
/openapi.json
/redoc
```

When `config.auth.enabled = false` (default for local dev): middleware is a no-op pass-through.

### 2.3 New Routes

**`GET /api/sources`** — `api/routes/sources.py`
- Reads `app.state.config["sources"]` — no DB call
- Returns list of source objects: `name`, `type`, `url`, `mode`
- Response model: `SourcesResponse { sources: list[SourceInfo] }`

**`GET /api/agents`** — `api/routes/agents.py`
- Returns `501 Not Implemented` via `HTTPException(501, "agents API not available in v1.0")`
- Global handler formats to standard error body with `code: "http_501"`

**`POST /api/agents/trigger`** — same file
- Same: `501 Not Implemented`

Both routers wired into `main.py` with `prefix="/api"`.

### 2.4 Health Route

`api/routes/health.py` updated to accept `Request` and run real dependency checks.

Checks run in parallel via `asyncio.gather` with individual 5s timeouts:

| Dependency | Check method |
|---|---|
| PostgreSQL | `SELECT 1` via pool |
| Qdrant | `get_collection(collection_name)` |
| OpenAI | `OPENAI_API_KEY` env var present (no network call) |
| Claude | `ANTHROPIC_API_KEY` env var present (no network call) |

Each check returns `{"status": "ok"}` or `{"status": "error", "detail": "<reason>"}`.

HTTP response:
- `200` if all checks pass (`status: "healthy"`)
- `503` if any check fails (`status: "degraded"`)
- Full dependency map always included in body regardless of status

### 2.5 Audit Trail — Search

`api/routes/search.py` gains one `append_audit_log` call after a successful response:

```python
await append_audit_log(pool, "search_executed", {
    "query": body.query,
    "results": len(response.results),
    "fallback_used": response.fallback_used,
})
```

This completes the full audit coverage per CLAUDE.md:
- `search_executed` ← added in M6
- `rca_created`, `task_created` ← analyze.py (M4)
- `task_approved`, `task_dismissed` ← tasks.py (M5)
- `anomaly_reviewed` ← anomalies.py (M5)
- `anomaly_detected` ← ingestion pipeline (M2, out of M6 scope)

---

## 3. Data Flow

```
Request
  → add_request_id middleware (sets ContextVar + response header)
  → auth_middleware (401 if enabled + invalid key)
  → route handler
      → raises HTTPException or Exception on failure
  → global exception handler → standard {error, code, request_id, timestamp}
  → response
```

---

## 4. Error Handling

- All unhandled exceptions caught by `Exception` handler → `500 internal_error`
- HTTPExceptions reformatted by `HTTPException` handler — existing routes unchanged
- Auth failures return `401` before reaching route handlers
- Health check failures per-dependency are isolated — one failure doesn't crash others
- Health returns `503` (not `500`) to signal degraded state vs internal error

---

## 5. Testing (TDD)

All features built red-green with `pytest-asyncio` + `httpx.AsyncClient`. Mocks via `unittest.mock.AsyncMock` for DB pool, Qdrant client, LLM clients.

| Test | Assertion |
|---|---|
| 404 error format | body has `error`, `code`, `request_id`, `timestamp`; no `detail` field |
| 422 validation error format | same shape |
| 500 unhandled exception format | `code: "internal_error"`, status 500 |
| Auth — no key, enabled | 401 returned |
| Auth — wrong key, enabled | 401 returned |
| Auth — correct key | request passes through |
| Auth — disabled | request passes regardless of key |
| Auth — `/api/health` bypass | no auth check even when enabled |
| `GET /api/sources` | returns sources from config |
| `GET /api/agents` | 501 with standard error body |
| `POST /api/agents/trigger` | 501 with standard error body |
| Health — all healthy | status 200, `"status": "healthy"` |
| Health — pg failure | status 503, `"status": "degraded"`, pg shows error |
| Health — qdrant failure | status 503, qdrant shows error, others still shown |
| Search audit | `append_audit_log` called with `"search_executed"` after success |

---

## 6. Files Changed

| File | Change |
|---|---|
| `api/main.py` | Add `ContextVar`, global exception handlers, auth middleware, wire new routers |
| `api/routes/health.py` | Real dependency checks, accept `Request` |
| `api/routes/search.py` | Add `search_executed` audit call |
| `api/routes/sources.py` | New — `GET /api/sources` |
| `api/routes/agents.py` | New — `GET /api/agents` + `POST /api/agents/trigger` stubs |
| `tests/test_m6_*.py` | New test files per feature area |

No DB schema changes. No config.yaml changes.
