# M4 + M5 Design: RCA, Tasks, Anomaly Detection

**Date:** 2026-05-06  
**Scope:** M4 (LLM Root Cause Analysis + Task Queue) and M5 (Anomaly Detection) implemented together  
**Approach:** Option C — flat async functions + `RCAContext` Pydantic model, config-driven context assembly

---

## 1. Context

M0–M3 are complete. The DB has `sync_cursors` and `logs` tables. The intelligence layer has `search.py`. The ingestion pipeline (`IngestionWorker`) chunks, embeds, upserts to Qdrant, and inserts to PostgreSQL. Models for `RootCauseAnalysis`, `ActionableTask`, and `AnomalyResult` are already defined.

M4+M5 add the LLM analysis layer, anomaly scoring inline in ingestion, and all associated API routes and DB tables.

---

## 2. DB Schema — Migration 003

One migration file: `db/migrations/003_intelligence.sql`

```sql
CREATE TABLE IF NOT EXISTS rca (
    id                TEXT        PRIMARY KEY,
    log_id            TEXT        NOT NULL REFERENCES logs(id),
    trace_id          TEXT,
    summary           TEXT        NOT NULL,
    root_cause        TEXT        NOT NULL,
    affected_services JSONB       NOT NULL DEFAULT '[]',
    confidence        FLOAT       NOT NULL,
    suggested_fixes   JSONB       NOT NULL DEFAULT '[]',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rca_log_id   ON rca (log_id);
CREATE INDEX IF NOT EXISTS idx_rca_trace_id ON rca (trace_id);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT        PRIMARY KEY,
    rca_id      TEXT        NOT NULL REFERENCES rca(id),
    log_id      TEXT        NOT NULL REFERENCES logs(id),
    title       TEXT        NOT NULL,
    description TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending',
    priority    TEXT        NOT NULL DEFAULT 'medium',
    agent_id    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks (priority);
CREATE INDEX IF NOT EXISTS idx_tasks_rca_id   ON tasks (rca_id);

CREATE TABLE IF NOT EXISTS anomalies (
    id           TEXT        PRIMARY KEY,
    log_id       TEXT        NOT NULL REFERENCES logs(id),
    score        FLOAT       NOT NULL,
    is_anomaly   BOOLEAN     NOT NULL,
    threshold    FLOAT       NOT NULL,
    reviewed     BOOLEAN     NOT NULL DEFAULT FALSE,
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomalies_log_id   ON anomalies (log_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_reviewed ON anomalies (reviewed);

CREATE TABLE IF NOT EXISTS audit_log (
    id         TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    event_type TEXT        NOT NULL,
    payload    JSONB       NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);
```

Valid `status` values enforced at application level: `pending`, `approved`, `in_progress`, `resolved`, `dismissed`.  
Valid `event_type` values: `rca_created`, `task_created`, `task_approved`, `task_dismissed`, `anomaly_detected`, `anomaly_reviewed`, `search_executed`.

---

## 3. Data Layer — `db/postgres.py` additions

New async helper functions added to the existing `db/postgres.py`:

```python
# RCA
async def insert_rca(pool, rca: RootCauseAnalysis) -> None
async def get_rca_by_log_ids(pool, log_ids: list[str]) -> list[RootCauseAnalysis]

# Tasks
async def insert_task(pool, task: ActionableTask) -> None
async def get_tasks(pool, status: str | None, priority: str | None, limit: int, offset: int) -> tuple[list[ActionableTask], int]
async def update_task_status(pool, task_id: str, new_status: str) -> ActionableTask | None

# Anomalies
async def insert_anomaly(pool, anomaly: AnomalyResult) -> None
async def get_anomalies(pool, reviewed: bool | None, is_anomaly: bool | None, limit: int, offset: int) -> tuple[list[AnomalyResult], int]
async def mark_anomaly_reviewed(pool, anomaly_id: str) -> AnomalyResult | None

# Trace
async def get_logs_by_trace_id(pool, trace_id: str, limit: int = 200) -> list[LogEvent]

# Audit
async def append_audit_log(pool, event_type: str, payload: dict) -> None
```

`get_tasks` and `get_anomalies` return `(rows, total_count)` for pagination. `update_task_status` and `mark_anomaly_reviewed` return `None` if the row does not exist (routes return 404).

---

## 4. Intelligence Layer

### 4.1 `intelligence/analyze.py`

**`RCAContext` model** — carries assembled context for a single RCA call:

```python
class RCAContext(BaseModel):
    target: LogEvent
    semantic_neighbors: list[LogEvent] = []  # Qdrant KNN hits
    trace_logs: list[LogEvent] = []          # logs sharing trace_id
```

**Functions:**

```python
async def build_rca_context(
    log_id: str,
    pool,
    openai_client: AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    config: dict,          # rca section of config.yaml
    collection: str,
) -> RCAContext
```

Fetches target log from PG. Conditionally fetches semantic neighbors (`config["rca"]["semantic_neighbors"]`) up to `max_semantic_k`. Conditionally fetches trace logs (`config["rca"]["trace_logs"]`) up to `max_trace_logs`. If target log not found, raises `ValueError`.

```python
async def run_rca(
    context: RCAContext,
    anthropic_client: AsyncAnthropic,
    config: dict,
) -> RootCauseAnalysis
```

Builds a structured prompt from context — sections are conditionally included based on what `RCAContext` contains. Calls Claude (`config["rca"]["model"]`) with a 30s timeout (`config["rca"]["timeout_seconds"]`). Parses the JSON response into `RootCauseAnalysis`. On timeout or parse failure, raises `RuntimeError` (route returns 502).

Prompt structure:
```
You are a log analysis expert. Analyse the following log event and return a JSON object matching this schema: {...}.

## Target Log
{target log as JSON}

## Semantically Similar Logs (up to {k})   ← only if semantic_neighbors non-empty
{...}

## Trace Logs (same trace_id)              ← only if trace_logs non-empty
{...}
```

```python
async def create_tasks_from_rca(
    rca: RootCauseAnalysis,
    pool,
) -> list[ActionableTask]
```

Creates one `ActionableTask` per `suggested_fix`, priority derived from RCA confidence (≥0.8 → HIGH, ≥0.5 → MEDIUM, else LOW). Inserts all tasks via `insert_task`. Returns the list.

### 4.2 `intelligence/anomaly.py`

```python
async def score_batch(
    events: list[LogEvent],
    query_vectors: list[list[float]],  # one per event — first-chunk vector from ingestion
    qdrant_client: AsyncQdrantClient,
    config: dict,          # anomaly section of config.yaml
    collection: str,
) -> list[AnomalyResult]
```

`query_vectors` is aligned with `events` by index. The ingestion pipeline already computes one embedding per chunk; `_process_batch()` extracts the first chunk's vector for each event and passes it here — no re-embedding. For each event: queries Qdrant for K nearest neighbors using its pre-computed vector (`config["anomaly"]["knn_k"]`, default 10). Computes average similarity of the K hits. `is_anomaly = avg_similarity < config["anomaly"]["threshold"]` (default 0.72). `score = 1.0 - avg_similarity`. Returns one `AnomalyResult` per event.

### 4.3 `intelligence/correlate.py`

```python
class CorrelateResponse(BaseModel):
    logs_by_service: dict[str, list[LogEvent]]
    rca_records: list[RootCauseAnalysis]
    trace_summary: str | None = None      # populated only when fresh_analysis=True

async def correlate_trace(
    trace_id: str,
    fresh_analysis: bool,
    pool,
    openai_client: AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    anthropic_client: AsyncAnthropic,
    config: dict,
) -> CorrelateResponse
```

1. Fetch all logs for `trace_id` via `get_logs_by_trace_id` (up to 200).
2. Group by `service` into `logs_by_service`.
3. Fetch existing RCAs via `get_rca_by_log_ids`.
4. If `fresh_analysis=True`: build a trace-level prompt summarising all services and call Claude for a `trace_summary` string. Uses the same timeout as RCA.
5. Return `CorrelateResponse`.

---

## 5. Ingestion Pipeline Changes

`IngestionWorker.__init__` gains one new parameter: `anomaly_config: dict` (the `anomaly:` section of `config.yaml`).

`_process_batch()` new step order:

```
chunk → embed → upsert Qdrant → insert PG → score_batch() → insert_anomaly() × N → mark embedded_at
```

Anomaly scoring runs after upsert so vectors are present in Qdrant for the KNN query. Each `AnomalyResult` is written to DB via `insert_anomaly`. Scoring errors are caught with `except Exception` — logged as warnings, batch continues. The `mark embedded_at` step is unaffected by scoring failures.

`api/main.py` passes `anomaly_config=_config.get("anomaly", {})` when constructing `IngestionWorker`.

---

## 6. API Routes

All new routes registered in `api/main.py`. The `anthropic_client: AsyncAnthropic` is added to `app.state` in lifespan alongside the existing `openai_client`.

### `POST /api/analyze`

```
Body:     { "log_id": str, "create_tasks": bool = true }
Response: { "rca": RootCauseAnalysis, "tasks": list[ActionableTask] }
Errors:   404 if log_id not found, 502 on LLM timeout/parse failure
```

1. `build_rca_context(log_id, ...)`
2. `run_rca(context, ...)`
3. `insert_rca(pool, rca)`
4. `append_audit_log("rca_created", {"rca_id": rca.id, "log_id": log_id})`
5. If `create_tasks=True`: `create_tasks_from_rca(rca, pool)` + `append_audit_log("task_created", ...)` per task
6. Return response

### `GET /api/correlate/{trace_id}`

```
Query:    fresh_analysis: bool = false
Response: CorrelateResponse
Errors:   404 if no logs found for trace_id
```

### `GET /api/anomalies`

```
Query:    reviewed: bool | null, is_anomaly: bool | null, limit: int = 50, offset: int = 0
Response: { "results": list[AnomalyResult], "total": int }
```

### `POST /api/anomalies/{id}/review`

```
Response: { "anomaly": AnomalyResult }
Errors:   404 if not found
Side effect: append_audit_log("anomaly_reviewed", {"anomaly_id": id})
```

### `GET /api/tasks`

```
Query:    status: str | null, priority: str | null, limit: int = 50, offset: int = 0
Response: { "results": list[ActionableTask], "total": int }
```

### `POST /api/tasks/{id}/approve`

```
Response: { "task": ActionableTask }
Errors:   404 if not found, 409 if status != "pending"
Side effect: append_audit_log("task_approved", {"task_id": id})
```

### `POST /api/tasks/{id}/dismiss`

```
Response: { "task": ActionableTask }
Errors:   404 if not found, 409 if status not in {"pending", "approved"}
Side effect: append_audit_log("task_dismissed", {"task_id": id})
```

---

## 7. Config Changes

Additions to `config.yaml`:

```yaml
rca:
  semantic_neighbors: true
  max_semantic_k: 5
  trace_logs: true
  max_trace_logs: 20
  model: claude-sonnet-4-20250514
  timeout_seconds: 30

anomaly:
  knn_k: 10
  threshold: 0.72

correlate:
  fresh_analysis: false        # default; overridden per-request via query param
  max_trace_logs: 200
```

---

## 8. Testing Strategy

All tests follow the existing TDD pattern — external clients (Anthropic, OpenAI, Qdrant, asyncpg) are mocked. No real DB or network calls.

| File | Coverage |
|---|---|
| `tests/db/test_postgres.py` | insert_rca, get_rca_by_log_ids, insert_task, get_tasks (filter combos), update_task_status (valid + invalid row), insert_anomaly, get_anomalies, mark_anomaly_reviewed, get_logs_by_trace_id, append_audit_log |
| `tests/intelligence/test_analyze.py` | build_rca_context with each source on/off; run_rca with mocked Anthropic (success + timeout + parse error); create_tasks_from_rca priority derivation |
| `tests/intelligence/test_anomaly.py` | score_batch above/below threshold; empty batch; single event; scoring error does not raise |
| `tests/intelligence/test_correlate.py` | correlate_trace with fresh_analysis=False and True; 404 path (no logs) |
| `tests/api/test_analyze.py` | POST /api/analyze happy path; 404 log not found; create_tasks=false; 502 on LLM error |
| `tests/api/test_correlate.py` | GET /api/correlate/{trace_id} both fresh_analysis modes; 404 |
| `tests/api/test_anomalies.py` | GET filters (reviewed, is_anomaly, pagination); POST review happy path; 404 |
| `tests/api/test_tasks.py` | GET filters (status, priority, pagination); approve happy path; dismiss happy path; 409 invalid transition; 404 |
| `tests/ingestion/test_pipeline.py` | Extended: anomaly scoring called after upsert; scoring exception does not abort batch; mark embedded_at still runs |

---

## 9. File Manifest

**New files:**
- `db/migrations/003_intelligence.sql`
- `intelligence/analyze.py`
- `intelligence/anomaly.py`
- `intelligence/correlate.py`
- `api/routes/analyze.py`
- `api/routes/correlate.py`
- `api/routes/anomalies.py`
- `api/routes/tasks.py`
- `tests/intelligence/test_analyze.py`
- `tests/intelligence/test_anomaly.py`
- `tests/intelligence/test_correlate.py`
- `tests/api/test_analyze.py`
- `tests/api/test_correlate.py`
- `tests/api/test_anomalies.py`
- `tests/api/test_tasks.py`

**Modified files:**
- `db/postgres.py` — 9 new helper functions
- `ingestion/pipeline.py` — anomaly scoring step + `anomaly_config` param; pass first-chunk vectors to `score_batch`
- `api/main.py` — `AsyncAnthropic` client in lifespan, 4 new routers
- `config.yaml` — rca, anomaly, correlate sections
- `pyproject.toml` — add `anthropic` package dependency
