# M4+M5 RCA, Tasks, Anomaly Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-powered root cause analysis, human-gated task queue, and inline anomaly detection to LogIQ.

**Architecture:** Flat async functions in `intelligence/` (matching `search.py` style). Anomaly scoring runs inline in `IngestionWorker._process_batch()` after Qdrant upsert using pre-computed embeddings. RCA uses configurable context assembly (`RCAContext` model). Four new API route files, one DB migration.

**Tech Stack:** FastAPI, asyncpg, Anthropic SDK (`anthropic`), Qdrant, OpenAI (embeddings already wired), pytest-asyncio, httpx

---

## File Map

**New:**
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

**Modified:**
- `db/postgres.py` — 9 new helpers + 3 row mappers
- `ingestion/pipeline.py` — anomaly step + `anomaly_config` param
- `api/main.py` — anthropic client, config in state, 4 new routers
- `tests/api/conftest.py` — mock anthropic client
- `config.yaml` — rca/anomaly/correlate sections
- `pyproject.toml` — add `anthropic` dependency

---

## Task 1: DB Migration 003

**Files:**
- Create: `db/migrations/003_intelligence.sql`

- [ ] **Step 1: Write the migration**

```sql
-- db/migrations/003_intelligence.sql

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
    id          TEXT        PRIMARY KEY,
    log_id      TEXT        NOT NULL REFERENCES logs(id),
    score       FLOAT       NOT NULL,
    is_anomaly  BOOLEAN     NOT NULL,
    threshold   FLOAT       NOT NULL,
    reviewed    BOOLEAN     NOT NULL DEFAULT FALSE,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

- [ ] **Step 2: Commit**

```bash
git add db/migrations/003_intelligence.sql
git commit -m "feat: migration 003 — rca, tasks, anomalies, audit_log tables"
```

---

## Task 2: DB Helpers — RCA, Audit, Trace

**Files:**
- Modify: `db/postgres.py`
- Test: `tests/db/test_postgres.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/db/test_postgres.py`:

```python
# tests/db/test_postgres.py  (add to existing file)
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.rca import RootCauseAnalysis
from models.log_event import LogEvent, SeverityLevel


def _make_rca(**kwargs) -> RootCauseAnalysis:
    defaults = dict(
        log_id="log-001",
        trace_id="trace-abc",
        summary="Auth service failed",
        root_cause="DB connection pool exhausted",
        affected_services=["auth-service", "api-gateway"],
        confidence=0.9,
        suggested_fixes=["Increase pool size", "Add circuit breaker"],
    )
    return RootCauseAnalysis(**{**defaults, **kwargs})


def _make_log_event(**kwargs) -> LogEvent:
    defaults = dict(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="connection refused",
        source="loki",
        trace_id="trace-abc",
    )
    return LogEvent(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_insert_rca_executes_insert():
    from db.postgres import insert_rca
    rca = _make_rca()
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    await insert_rca(mock_pool, rca)

    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args[0]
    assert rca.id in call_args


@pytest.mark.asyncio
async def test_get_rca_by_log_ids_returns_empty_for_empty_input():
    from db.postgres import get_rca_by_log_ids
    result = await get_rca_by_log_ids(MagicMock(), [])
    assert result == []


@pytest.mark.asyncio
async def test_get_logs_by_trace_id_queries_correct_column():
    from db.postgres import get_logs_by_trace_id
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    result = await get_logs_by_trace_id(mock_pool, "trace-abc", limit=50)

    assert result == []
    call_sql = mock_conn.fetch.call_args[0][0]
    assert "trace_id" in call_sql


@pytest.mark.asyncio
async def test_append_audit_log_inserts_event():
    from db.postgres import append_audit_log
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    await append_audit_log(mock_pool, "rca_created", {"rca_id": "rca-001"})

    mock_conn.execute.assert_called_once()
    assert "rca_created" in mock_conn.execute.call_args[0]
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/db/test_postgres.py::test_insert_rca_executes_insert tests/db/test_postgres.py::test_get_rca_by_log_ids_returns_empty_for_empty_input tests/db/test_postgres.py::test_get_logs_by_trace_id_queries_correct_column tests/db/test_postgres.py::test_append_audit_log_inserts_event -v
```

Expected: `ImportError` or `AttributeError` — functions not yet defined.

- [ ] **Step 3: Add helpers to `db/postgres.py`**

Add these imports at the top of `db/postgres.py` (after existing imports):

```python
import json

from models.rca import RootCauseAnalysis
```

Add these functions at the bottom of `db/postgres.py`:

```python
def _row_to_rca(row) -> RootCauseAnalysis:
    return RootCauseAnalysis(
        id=row["id"],
        log_id=row["log_id"],
        trace_id=row["trace_id"],
        summary=row["summary"],
        root_cause=row["root_cause"],
        affected_services=list(row["affected_services"]),
        confidence=row["confidence"],
        suggested_fixes=list(row["suggested_fixes"]),
        created_at=row["created_at"],
    )


async def insert_rca(pool: asyncpg.Pool, rca: RootCauseAnalysis) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO rca
                (id, log_id, trace_id, summary, root_cause,
                 affected_services, confidence, suggested_fixes, created_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8::jsonb, $9)
            """,
            rca.id, rca.log_id, rca.trace_id, rca.summary, rca.root_cause,
            json.dumps(rca.affected_services), rca.confidence,
            json.dumps(rca.suggested_fixes), rca.created_at,
        )


async def get_rca_by_log_ids(pool: asyncpg.Pool, log_ids: list[str]) -> list[RootCauseAnalysis]:
    if not log_ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM rca WHERE log_id = ANY($1)", log_ids)
    return [_row_to_rca(row) for row in rows]


async def get_logs_by_trace_id(pool: asyncpg.Pool, trace_id: str, limit: int = 200) -> list[LogEvent]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM logs WHERE trace_id = $1 ORDER BY timestamp ASC LIMIT $2",
            trace_id, limit,
        )
    return [_row_to_log_event(row) for row in rows]


async def append_audit_log(pool: asyncpg.Pool, event_type: str, payload: dict) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO audit_log (event_type, payload) VALUES ($1, $2::jsonb)",
            event_type, json.dumps(payload),
        )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/db/test_postgres.py::test_insert_rca_executes_insert tests/db/test_postgres.py::test_get_rca_by_log_ids_returns_empty_for_empty_input tests/db/test_postgres.py::test_get_logs_by_trace_id_queries_correct_column tests/db/test_postgres.py::test_append_audit_log_inserts_event -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add db/postgres.py tests/db/test_postgres.py
git commit -m "feat: db/postgres.py — insert_rca, get_rca_by_log_ids, get_logs_by_trace_id, append_audit_log (TDD)"
```

---

## Task 3: DB Helpers — Tasks

**Files:**
- Modify: `db/postgres.py`
- Test: `tests/db/test_postgres.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/db/test_postgres.py`:

```python
from models.task import ActionableTask, TaskStatus, TaskPriority


def _make_task(**kwargs) -> ActionableTask:
    defaults = dict(
        rca_id="rca-001",
        log_id="log-001",
        title="Increase DB pool size",
        description="Increase the connection pool from 10 to 50",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
    )
    return ActionableTask(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_insert_task_executes_insert():
    from db.postgres import insert_task
    task = _make_task()
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    await insert_task(mock_pool, task)

    mock_conn.execute.assert_called_once()
    assert task.id in mock_conn.execute.call_args[0]


@pytest.mark.asyncio
async def test_get_tasks_returns_empty_list_when_no_rows():
    from db.postgres import get_tasks
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchval = AsyncMock(return_value=0)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    tasks, total = await get_tasks(mock_pool, status=None, priority=None, limit=50, offset=0)

    assert tasks == []
    assert total == 0


@pytest.mark.asyncio
async def test_update_task_status_returns_none_when_not_found():
    from db.postgres import update_task_status
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    result = await update_task_status(mock_pool, "nonexistent-id", "approved")

    assert result is None
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/db/test_postgres.py::test_insert_task_executes_insert tests/db/test_postgres.py::test_get_tasks_returns_empty_list_when_no_rows tests/db/test_postgres.py::test_update_task_status_returns_none_when_not_found -v
```

Expected: `ImportError` — functions not yet defined.

- [ ] **Step 3: Add task helpers to `db/postgres.py`**

Add import at top:
```python
from models.task import ActionableTask, TaskPriority, TaskStatus
```

Add these functions:

```python
def _row_to_task(row) -> ActionableTask:
    return ActionableTask(
        id=row["id"],
        rca_id=row["rca_id"],
        log_id=row["log_id"],
        title=row["title"],
        description=row["description"],
        status=TaskStatus(row["status"]),
        priority=TaskPriority(row["priority"]),
        agent_id=row["agent_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def insert_task(pool: asyncpg.Pool, task: ActionableTask) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tasks
                (id, rca_id, log_id, title, description, status, priority, agent_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            task.id, task.rca_id, task.log_id, task.title, task.description,
            task.status.value, task.priority.value, task.agent_id,
            task.created_at, task.updated_at,
        )


async def get_tasks(
    pool: asyncpg.Pool,
    status: str | None,
    priority: str | None,
    limit: int,
    offset: int,
) -> tuple[list[ActionableTask], int]:
    conditions: list[str] = []
    params: list = []
    if status is not None:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    if priority is not None:
        params.append(priority)
        conditions.append(f"priority = ${len(params)}")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    count_params = params[:]
    params += [limit, offset]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}",
            *params,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tasks {where}", *count_params)
    return [_row_to_task(row) for row in rows], (total or 0)


async def update_task_status(
    pool: asyncpg.Pool, task_id: str, new_status: str
) -> ActionableTask | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE tasks SET status = $1, updated_at = NOW() WHERE id = $2 RETURNING *",
            new_status, task_id,
        )
    return _row_to_task(row) if row else None
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/db/test_postgres.py::test_insert_task_executes_insert tests/db/test_postgres.py::test_get_tasks_returns_empty_list_when_no_rows tests/db/test_postgres.py::test_update_task_status_returns_none_when_not_found -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add db/postgres.py tests/db/test_postgres.py
git commit -m "feat: db/postgres.py — insert_task, get_tasks, update_task_status (TDD)"
```

---

## Task 4: DB Helpers — Anomalies

**Files:**
- Modify: `db/postgres.py`
- Test: `tests/db/test_postgres.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/db/test_postgres.py`:

```python
from models.anomaly import AnomalyResult


def _make_anomaly(**kwargs) -> AnomalyResult:
    defaults = dict(
        log_id="log-001",
        score=0.4,
        is_anomaly=True,
        threshold=0.72,
        reviewed=False,
    )
    return AnomalyResult(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_insert_anomaly_executes_insert():
    from db.postgres import insert_anomaly
    anomaly = _make_anomaly()
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    await insert_anomaly(mock_pool, anomaly)

    mock_conn.execute.assert_called_once()
    assert anomaly.id in mock_conn.execute.call_args[0]


@pytest.mark.asyncio
async def test_get_anomalies_returns_empty_when_no_rows():
    from db.postgres import get_anomalies
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchval = AsyncMock(return_value=0)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    anomalies, total = await get_anomalies(mock_pool, reviewed=None, is_anomaly=None, limit=50, offset=0)

    assert anomalies == []
    assert total == 0


@pytest.mark.asyncio
async def test_mark_anomaly_reviewed_returns_none_when_not_found():
    from db.postgres import mark_anomaly_reviewed
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)))

    result = await mark_anomaly_reviewed(mock_pool, "nonexistent-id")

    assert result is None
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/db/test_postgres.py::test_insert_anomaly_executes_insert tests/db/test_postgres.py::test_get_anomalies_returns_empty_when_no_rows tests/db/test_postgres.py::test_mark_anomaly_reviewed_returns_none_when_not_found -v
```

Expected: `ImportError`.

- [ ] **Step 3: Add anomaly helpers to `db/postgres.py`**

Add import at top:
```python
from models.anomaly import AnomalyResult
```

Add these functions:

```python
def _row_to_anomaly(row) -> AnomalyResult:
    return AnomalyResult(
        id=row["id"],
        log_id=row["log_id"],
        score=row["score"],
        is_anomaly=row["is_anomaly"],
        threshold=row["threshold"],
        reviewed=row["reviewed"],
        detected_at=row["detected_at"],
    )


async def insert_anomaly(pool: asyncpg.Pool, anomaly: AnomalyResult) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO anomalies (id, log_id, score, is_anomaly, threshold, reviewed, detected_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO NOTHING
            """,
            anomaly.id, anomaly.log_id, anomaly.score, anomaly.is_anomaly,
            anomaly.threshold, anomaly.reviewed, anomaly.detected_at,
        )


async def get_anomalies(
    pool: asyncpg.Pool,
    reviewed: bool | None,
    is_anomaly: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[AnomalyResult], int]:
    conditions: list[str] = []
    params: list = []
    if reviewed is not None:
        params.append(reviewed)
        conditions.append(f"reviewed = ${len(params)}")
    if is_anomaly is not None:
        params.append(is_anomaly)
        conditions.append(f"is_anomaly = ${len(params)}")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    count_params = params[:]
    params += [limit, offset]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM anomalies {where} ORDER BY detected_at DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}",
            *params,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM anomalies {where}", *count_params)
    return [_row_to_anomaly(row) for row in rows], (total or 0)


async def mark_anomaly_reviewed(pool: asyncpg.Pool, anomaly_id: str) -> AnomalyResult | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE anomalies SET reviewed = TRUE WHERE id = $1 RETURNING *",
            anomaly_id,
        )
    return _row_to_anomaly(row) if row else None
```

- [ ] **Step 4: Run all DB tests**

```bash
pytest tests/db/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add db/postgres.py tests/db/test_postgres.py
git commit -m "feat: db/postgres.py — insert_anomaly, get_anomalies, mark_anomaly_reviewed (TDD)"
```

---

## Task 5: Install `anthropic` + `intelligence/analyze.py`

**Files:**
- Create: `intelligence/analyze.py`
- Create: `tests/intelligence/test_analyze.py`

- [ ] **Step 1: Install `anthropic` package**

```bash
pip install anthropic
```

Verify: `python -c "from anthropic import AsyncAnthropic; print('ok')"` should print `ok`.

- [ ] **Step 2: Write failing tests**

```python
# tests/intelligence/test_analyze.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel
from models.rca import RootCauseAnalysis


def _make_event(**kwargs) -> LogEvent:
    defaults = dict(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="connection refused to db:5432",
        source="loki",
        trace_id="trace-abc",
    )
    return LogEvent(**{**defaults, **kwargs})


_RCA_CONFIG = {
    "semantic_neighbors": True,
    "max_semantic_k": 5,
    "trace_logs": True,
    "max_trace_logs": 20,
    "model": "claude-sonnet-4-20250514",
    "timeout_seconds": 30,
}

_CLAUDE_RESPONSE_JSON = json.dumps({
    "summary": "Auth service DB connection failure",
    "root_cause": "Connection pool exhausted under load",
    "affected_services": ["auth-service"],
    "confidence": 0.9,
    "suggested_fixes": ["Increase pool size", "Add circuit breaker"],
})


@pytest.mark.asyncio
async def test_build_rca_context_fetches_target_log():
    from intelligence.analyze import build_rca_context, RCAContext
    event = _make_event()

    with patch("intelligence.analyze.fetch_logs_by_ids", return_value=[event]), \
         patch("intelligence.analyze.embed_texts", return_value=[[0.1] * 1536]), \
         patch("intelligence.analyze.search_vectors", return_value=[("log-002", 0.85)]), \
         patch("intelligence.analyze.fetch_logs_by_ids") as mock_fetch:
        mock_fetch.side_effect = [[event], [_make_event(id="log-002")]]

        ctx = await build_rca_context(
            log_id="log-001",
            pool=MagicMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            config=_RCA_CONFIG,
            collection="log_events",
        )

    assert ctx.target.id == "log-001"


@pytest.mark.asyncio
async def test_build_rca_context_raises_value_error_when_log_not_found():
    from intelligence.analyze import build_rca_context

    with patch("intelligence.analyze.fetch_logs_by_ids", return_value=[]):
        with pytest.raises(ValueError, match="log-999"):
            await build_rca_context(
                log_id="log-999",
                pool=MagicMock(),
                openai_client=AsyncMock(),
                qdrant_client=AsyncMock(),
                config=_RCA_CONFIG,
                collection="log_events",
            )


@pytest.mark.asyncio
async def test_build_rca_context_skips_semantic_when_disabled():
    from intelligence.analyze import build_rca_context
    event = _make_event()
    config = {**_RCA_CONFIG, "semantic_neighbors": False, "trace_logs": False}

    with patch("intelligence.analyze.fetch_logs_by_ids", return_value=[event]) as mock_fetch, \
         patch("intelligence.analyze.embed_texts") as mock_embed:

        ctx = await build_rca_context(
            log_id="log-001",
            pool=MagicMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            config=config,
            collection="log_events",
        )

    mock_embed.assert_not_called()
    assert ctx.semantic_neighbors == []
    assert ctx.trace_logs == []


@pytest.mark.asyncio
async def test_run_rca_parses_claude_response():
    from intelligence.analyze import run_rca, RCAContext
    event = _make_event()
    ctx = RCAContext(target=event)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_CLAUDE_RESPONSE_JSON)]
    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(return_value=mock_message)

    rca = await run_rca(ctx, mock_anthropic, _RCA_CONFIG)

    assert rca.log_id == "log-001"
    assert rca.confidence == 0.9
    assert len(rca.suggested_fixes) == 2


@pytest.mark.asyncio
async def test_run_rca_raises_runtime_error_on_timeout():
    import asyncio
    from intelligence.analyze import run_rca, RCAContext
    ctx = RCAContext(target=_make_event())
    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=asyncio.TimeoutError)

    with pytest.raises(RuntimeError, match="timed out"):
        await run_rca(ctx, mock_anthropic, _RCA_CONFIG)


@pytest.mark.asyncio
async def test_create_tasks_from_rca_derives_priority_from_confidence():
    from intelligence.analyze import create_tasks_from_rca
    rca = RootCauseAnalysis(
        log_id="log-001",
        summary="s",
        root_cause="r",
        confidence=0.9,
        suggested_fixes=["Fix A", "Fix B"],
    )

    with patch("intelligence.analyze.insert_task", return_value=None):
        tasks = await create_tasks_from_rca(rca, MagicMock())

    assert len(tasks) == 2
    assert all(t.priority.value == "high" for t in tasks)


@pytest.mark.asyncio
async def test_create_tasks_from_rca_medium_priority_for_mid_confidence():
    from intelligence.analyze import create_tasks_from_rca
    rca = RootCauseAnalysis(
        log_id="log-001",
        summary="s",
        root_cause="r",
        confidence=0.6,
        suggested_fixes=["Fix A"],
    )

    with patch("intelligence.analyze.insert_task", return_value=None):
        tasks = await create_tasks_from_rca(rca, MagicMock())

    assert tasks[0].priority.value == "medium"
```

- [ ] **Step 3: Run tests — expect failures**

```bash
pytest tests/intelligence/test_analyze.py -v
```

Expected: `ModuleNotFoundError: No module named 'intelligence.analyze'`

- [ ] **Step 4: Implement `intelligence/analyze.py`**

```python
# intelligence/analyze.py
from __future__ import annotations

import asyncio
import json
import re

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

from db.postgres import fetch_logs_by_ids, get_logs_by_trace_id, insert_task
from db.qdrant import search_vectors
from ingestion.pipeline import embed_texts
from models.log_event import LogEvent
from models.rca import RootCauseAnalysis
from models.task import ActionableTask, TaskPriority


class RCAContext(BaseModel):
    target: LogEvent
    semantic_neighbors: list[LogEvent] = []
    trace_logs: list[LogEvent] = []


def _build_prompt(context: RCAContext) -> str:
    schema = (
        '{"summary": str, "root_cause": str, "affected_services": list[str], '
        '"confidence": float (0-1), "suggested_fixes": list[str]}'
    )
    parts = [
        f"You are a log analysis expert. Analyse the following log event and return ONLY a JSON object matching this schema: {schema}\n\n",
        f"## Target Log\n{context.target.model_dump_json(indent=2)}\n",
    ]
    if context.semantic_neighbors:
        parts.append(
            "## Semantically Similar Logs\n"
            + "\n".join(e.model_dump_json(indent=2) for e in context.semantic_neighbors)
            + "\n"
        )
    if context.trace_logs:
        parts.append(
            f"## Trace Logs (trace_id: {context.target.trace_id})\n"
            + "\n".join(e.model_dump_json(indent=2) for e in context.trace_logs)
            + "\n"
        )
    return "".join(parts)


async def build_rca_context(
    log_id: str,
    pool,
    openai_client: AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    config: dict,
    collection: str = "log_events",
) -> RCAContext:
    events = await fetch_logs_by_ids(pool, [log_id])
    if not events:
        raise ValueError(f"log {log_id} not found")
    target = events[0]

    semantic_neighbors: list[LogEvent] = []
    if config.get("semantic_neighbors", True):
        k = config.get("max_semantic_k", 5)
        [vector] = await embed_texts(openai_client, [target.message])
        hits = await search_vectors(qdrant_client, vector, None, limit=k + 1, collection=collection)
        neighbor_ids = [lid for lid, _ in hits if lid != log_id][:k]
        if neighbor_ids:
            semantic_neighbors = await fetch_logs_by_ids(pool, neighbor_ids)

    trace_logs: list[LogEvent] = []
    if config.get("trace_logs", True) and target.trace_id:
        limit = config.get("max_trace_logs", 20)
        all_trace = await get_logs_by_trace_id(pool, target.trace_id, limit)
        trace_logs = [e for e in all_trace if e.id != log_id]

    return RCAContext(target=target, semantic_neighbors=semantic_neighbors, trace_logs=trace_logs)


async def run_rca(
    context: RCAContext,
    anthropic_client: AsyncAnthropic,
    config: dict,
) -> RootCauseAnalysis:
    prompt = _build_prompt(context)
    try:
        response = await asyncio.wait_for(
            anthropic_client.messages.create(
                model=config.get("model", "claude-sonnet-4-20250514"),
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=config.get("timeout_seconds", 30),
        )
    except (asyncio.TimeoutError, TimeoutError):
        raise RuntimeError("RCA timed out")

    text = response.content[0].text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"Could not parse RCA response: {text[:200]}")
        data = json.loads(match.group())

    return RootCauseAnalysis(
        log_id=context.target.id,
        trace_id=context.target.trace_id,
        summary=data["summary"],
        root_cause=data["root_cause"],
        affected_services=data.get("affected_services", []),
        confidence=float(data["confidence"]),
        suggested_fixes=data.get("suggested_fixes", []),
    )


async def create_tasks_from_rca(
    rca: RootCauseAnalysis,
    pool,
) -> list[ActionableTask]:
    if rca.confidence >= 0.8:
        priority = TaskPriority.HIGH
    elif rca.confidence >= 0.5:
        priority = TaskPriority.MEDIUM
    else:
        priority = TaskPriority.LOW

    tasks = [
        ActionableTask(
            rca_id=rca.id,
            log_id=rca.log_id,
            title=fix[:120],
            description=fix,
            priority=priority,
        )
        for fix in rca.suggested_fixes
    ]
    for task in tasks:
        await insert_task(pool, task)
    return tasks
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/intelligence/test_analyze.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add intelligence/analyze.py tests/intelligence/test_analyze.py
git commit -m "feat: intelligence/analyze.py — RCAContext, build_rca_context, run_rca, create_tasks_from_rca (TDD)"
```

---

## Task 6: `intelligence/anomaly.py`

**Files:**
- Create: `intelligence/anomaly.py`
- Create: `tests/intelligence/test_anomaly.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/intelligence/test_anomaly.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel


def _make_event(id: str = "log-001", **kwargs) -> LogEvent:
    return LogEvent(
        id=id,
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="db connection refused",
        source="loki",
        **kwargs,
    )


_ANOMALY_CONFIG = {"knn_k": 10, "threshold": 0.72}


@pytest.mark.asyncio
async def test_score_batch_flags_anomaly_when_avg_similarity_below_threshold():
    from intelligence.anomaly import score_batch
    event = _make_event()
    # avg similarity = 0.5 → is_anomaly=True (below 0.72 threshold)
    neighbors = [("log-002", 0.5), ("log-003", 0.5)]

    with patch("intelligence.anomaly.search_vectors", return_value=neighbors):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    assert len(results) == 1
    assert results[0].is_anomaly is True
    assert results[0].log_id == "log-001"
    assert results[0].score == pytest.approx(0.5)  # 1.0 - 0.5


@pytest.mark.asyncio
async def test_score_batch_no_anomaly_when_avg_similarity_above_threshold():
    from intelligence.anomaly import score_batch
    event = _make_event()
    neighbors = [("log-002", 0.9), ("log-003", 0.85)]

    with patch("intelligence.anomaly.search_vectors", return_value=neighbors):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    assert results[0].is_anomaly is False


@pytest.mark.asyncio
async def test_score_batch_excludes_self_from_neighbors():
    from intelligence.anomaly import score_batch
    event = _make_event(id="log-001")
    # "log-001" is self — should be excluded; only log-002 remains
    hits = [("log-001", 1.0), ("log-002", 0.5)]

    with patch("intelligence.anomaly.search_vectors", return_value=hits):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    # avg_sim = 0.5 (self excluded), score = 0.5
    assert results[0].score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_score_batch_returns_empty_for_empty_input():
    from intelligence.anomaly import score_batch
    results = await score_batch(
        events=[],
        query_vectors=[],
        qdrant_client=AsyncMock(),
        config=_ANOMALY_CONFIG,
        collection="log_events",
    )
    assert results == []


@pytest.mark.asyncio
async def test_score_batch_treats_no_neighbors_as_anomaly():
    from intelligence.anomaly import score_batch
    event = _make_event()

    with patch("intelligence.anomaly.search_vectors", return_value=[]):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    assert results[0].is_anomaly is True
    assert results[0].score == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/intelligence/test_anomaly.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `intelligence/anomaly.py`**

```python
# intelligence/anomaly.py
from __future__ import annotations

from qdrant_client import AsyncQdrantClient

from db.qdrant import search_vectors
from models.anomaly import AnomalyResult
from models.log_event import LogEvent


async def score_batch(
    events: list[LogEvent],
    query_vectors: list[list[float]],
    qdrant_client: AsyncQdrantClient,
    config: dict,
    collection: str = "log_events",
) -> list[AnomalyResult]:
    if not events:
        return []

    k = config.get("knn_k", 10)
    threshold = config.get("threshold", 0.72)
    results: list[AnomalyResult] = []

    for event, vector in zip(events, query_vectors):
        hits = await search_vectors(qdrant_client, vector, None, limit=k + 1, collection=collection)
        neighbors = [(lid, score) for lid, score in hits if lid != event.id][:k]

        if not neighbors:
            avg_sim = 0.0
        else:
            avg_sim = sum(s for _, s in neighbors) / len(neighbors)

        results.append(
            AnomalyResult(
                log_id=event.id,
                score=round(1.0 - avg_sim, 6),
                is_anomaly=avg_sim < threshold,
                threshold=threshold,
            )
        )

    return results
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/intelligence/test_anomaly.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add intelligence/anomaly.py tests/intelligence/test_anomaly.py
git commit -m "feat: intelligence/anomaly.py — score_batch with KNN, self-exclusion, empty-batch guard (TDD)"
```

---

## Task 7: `intelligence/correlate.py`

**Files:**
- Create: `intelligence/correlate.py`
- Create: `tests/intelligence/test_correlate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/intelligence/test_correlate.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel
from models.rca import RootCauseAnalysis


def _make_event(id: str = "log-001", service: str = "auth-service", **kwargs) -> LogEvent:
    return LogEvent(
        id=id,
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service=service,
        environment="production",
        message="error occurred",
        source="loki",
        trace_id="trace-abc",
        **kwargs,
    )


_CONFIG = {
    "rca": {"model": "claude-sonnet-4-20250514", "timeout_seconds": 30},
    "correlate": {"max_trace_logs": 200},
}


@pytest.mark.asyncio
async def test_correlate_trace_raises_value_error_when_no_logs():
    from intelligence.correlate import correlate_trace

    with patch("intelligence.correlate.get_logs_by_trace_id", return_value=[]):
        with pytest.raises(ValueError, match="trace-xyz"):
            await correlate_trace(
                trace_id="trace-xyz",
                fresh_analysis=False,
                pool=MagicMock(),
                openai_client=AsyncMock(),
                qdrant_client=AsyncMock(),
                anthropic_client=AsyncMock(),
                config=_CONFIG,
            )


@pytest.mark.asyncio
async def test_correlate_trace_groups_logs_by_service():
    from intelligence.correlate import correlate_trace

    logs = [
        _make_event(id="log-001", service="auth-service"),
        _make_event(id="log-002", service="api-gateway"),
        _make_event(id="log-003", service="auth-service"),
    ]

    with patch("intelligence.correlate.get_logs_by_trace_id", return_value=logs), \
         patch("intelligence.correlate.get_rca_by_log_ids", return_value=[]):

        result = await correlate_trace(
            trace_id="trace-abc",
            fresh_analysis=False,
            pool=MagicMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            anthropic_client=AsyncMock(),
            config=_CONFIG,
        )

    assert set(result.logs_by_service.keys()) == {"auth-service", "api-gateway"}
    assert len(result.logs_by_service["auth-service"]) == 2
    assert result.trace_summary is None


@pytest.mark.asyncio
async def test_correlate_trace_returns_trace_summary_when_fresh_analysis():
    from intelligence.correlate import correlate_trace

    logs = [_make_event()]
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Root cause: DB overload")]
    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(return_value=mock_message)

    with patch("intelligence.correlate.get_logs_by_trace_id", return_value=logs), \
         patch("intelligence.correlate.get_rca_by_log_ids", return_value=[]):

        result = await correlate_trace(
            trace_id="trace-abc",
            fresh_analysis=True,
            pool=MagicMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            anthropic_client=mock_anthropic,
            config=_CONFIG,
        )

    assert result.trace_summary == "Root cause: DB overload"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/intelligence/test_correlate.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `intelligence/correlate.py`**

```python
# intelligence/correlate.py
from __future__ import annotations

import asyncio

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient

from db.postgres import get_logs_by_trace_id, get_rca_by_log_ids
from models.log_event import LogEvent
from models.rca import RootCauseAnalysis


class CorrelateResponse(BaseModel):
    logs_by_service: dict[str, list[LogEvent]]
    rca_records: list[RootCauseAnalysis]
    trace_summary: str | None = None


async def correlate_trace(
    trace_id: str,
    fresh_analysis: bool,
    pool,
    openai_client: AsyncOpenAI,
    qdrant_client: AsyncQdrantClient,
    anthropic_client: AsyncAnthropic,
    config: dict,
) -> CorrelateResponse:
    max_logs = config.get("correlate", {}).get("max_trace_logs", 200)
    logs = await get_logs_by_trace_id(pool, trace_id, max_logs)
    if not logs:
        raise ValueError(f"no logs for trace_id {trace_id}")

    logs_by_service: dict[str, list[LogEvent]] = {}
    for log in logs:
        logs_by_service.setdefault(log.service, []).append(log)

    rca_records = await get_rca_by_log_ids(pool, [log.id for log in logs])

    trace_summary: str | None = None
    if fresh_analysis:
        services_text = "\n".join(
            f"## {svc} ({len(evts)} log(s))\n"
            + "\n".join(e.model_dump_json() for e in evts[:5])
            for svc, evts in logs_by_service.items()
        )
        prompt = (
            f"Analyse this distributed trace (trace_id: {trace_id}) spanning "
            f"{len(logs_by_service)} service(s). Return a concise summary of what happened, "
            f"the likely root cause, and which service is the origin of failure.\n\n"
            f"{services_text}"
        )
        rca_cfg = config.get("rca", {})
        try:
            response = await asyncio.wait_for(
                anthropic_client.messages.create(
                    model=rca_cfg.get("model", "claude-sonnet-4-20250514"),
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=rca_cfg.get("timeout_seconds", 30),
            )
            trace_summary = response.content[0].text
        except (asyncio.TimeoutError, TimeoutError):
            raise RuntimeError("Trace analysis timed out")

    return CorrelateResponse(
        logs_by_service=logs_by_service,
        rca_records=rca_records,
        trace_summary=trace_summary,
    )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/intelligence/test_correlate.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add intelligence/correlate.py tests/intelligence/test_correlate.py
git commit -m "feat: intelligence/correlate.py — correlate_trace with fresh_analysis flag (TDD)"
```

---

## Task 8: Wire Anomaly Scoring into IngestionWorker

**Files:**
- Modify: `ingestion/pipeline.py`
- Test: `tests/ingestion/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/ingestion/test_pipeline.py`:

```python
# Add to existing test_pipeline.py

@pytest.mark.asyncio
async def test_process_batch_calls_score_batch_after_upsert():
    from ingestion.pipeline import IngestionWorker
    from models.anomaly import AnomalyResult
    from datetime import datetime, timezone

    event = LogEvent(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth",
        environment="prod",
        message="err",
        source="loki",
    )
    anomaly = AnomalyResult(log_id="log-001", score=0.4, is_anomaly=True, threshold=0.72)

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]), \
         patch("ingestion.pipeline.embed_texts", return_value=[[0.1] * 1536]), \
         patch("ingestion.pipeline.upsert_vectors"), \
         patch("ingestion.pipeline.mark_embedded"), \
         patch("ingestion.pipeline.score_batch", return_value=[anomaly]) as mock_score, \
         patch("ingestion.pipeline.insert_anomaly") as mock_insert:

        worker = IngestionWorker(
            pool=AsyncMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            anomaly_config={"knn_k": 10, "threshold": 0.72},
        )
        await worker._process_batch()

    mock_score.assert_called_once()
    mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_process_batch_continues_when_score_batch_raises():
    from ingestion.pipeline import IngestionWorker
    from datetime import datetime, timezone

    event = LogEvent(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth",
        environment="prod",
        message="err",
        source="loki",
    )

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]), \
         patch("ingestion.pipeline.embed_texts", return_value=[[0.1] * 1536]), \
         patch("ingestion.pipeline.upsert_vectors"), \
         patch("ingestion.pipeline.score_batch", side_effect=Exception("qdrant down")), \
         patch("ingestion.pipeline.mark_embedded") as mock_mark:

        worker = IngestionWorker(
            pool=AsyncMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            anomaly_config={"knn_k": 10, "threshold": 0.72},
        )
        result = await worker._process_batch()

    assert result is True
    mock_mark.assert_called_once()
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/ingestion/test_pipeline.py::test_process_batch_calls_score_batch_after_upsert tests/ingestion/test_pipeline.py::test_process_batch_continues_when_score_batch_raises -v
```

Expected: errors about missing params/imports.

- [ ] **Step 3: Update `ingestion/pipeline.py`**

Replace the entire file:

```python
# ingestion/pipeline.py
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import tiktoken
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from db.postgres import fetch_unembedded_logs, insert_anomaly, mark_embedded
from db.qdrant import upsert_vectors
from intelligence.anomaly import score_batch
from models.log_event import LogEvent

logger = logging.getLogger(__name__)

_ENCODER = tiktoken.get_encoding("cl100k_base")
_MAX_TOKENS = 512
_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


def chunk_message(text: str) -> list[str]:
    tokens = _ENCODER.encode(text)
    if len(tokens) <= _MAX_TOKENS:
        return [text]
    return [
        _ENCODER.decode(tokens[i : i + _MAX_TOKENS])
        for i in range(0, len(tokens), _MAX_TOKENS)
    ]


async def embed_texts(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


class IngestionWorker:
    def __init__(
        self,
        pool: Any,
        openai_client: AsyncOpenAI,
        qdrant_client: AsyncQdrantClient,
        poll_interval: float = 5.0,
        batch_size: int = 100,
        collection: str = "log_events",
        anomaly_config: dict | None = None,
    ) -> None:
        self._pool = pool
        self._openai = openai_client
        self._qdrant = qdrant_client
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._collection = collection
        self._anomaly_config = anomaly_config or {}
        self._task: asyncio.Task | None = None
        self._backoff = _BASE_BACKOFF

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                processed = await self._process_batch()
                self._backoff = _BASE_BACKOFF
                if not processed:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "IngestionWorker failure, retry in %.1fs: %s", self._backoff, exc
                )
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, _MAX_BACKOFF)

    async def _process_batch(self) -> bool:
        events = await fetch_unembedded_logs(self._pool, self._batch_size)
        if not events:
            return False

        items: list[tuple[LogEvent, int, str]] = [
            (event, i, chunk)
            for event in events
            for i, chunk in enumerate(chunk_message(event.message))
        ]

        embeddings = await embed_texts(self._openai, [text for _, _, text in items])

        chunk_counts: dict[str, int] = {}
        for event, _, _ in items:
            chunk_counts[event.id] = chunk_counts.get(event.id, 0) + 1

        points: list[PointStruct] = [
            PointStruct(
                id=event.id if chunk_counts[event.id] == 1
                else str(uuid.uuid5(uuid.NAMESPACE_OID, f"{event.id}:{i}")),
                vector=embedding,
                payload={
                    "log_id": event.id,
                    "timestamp_unix": event.timestamp.timestamp(),
                    "severity": event.severity.value,
                    "service": event.service,
                    "environment": event.environment,
                    "trace_id": event.trace_id,
                },
            )
            for (event, i, _), embedding in zip(items, embeddings)
        ]

        await upsert_vectors(self._qdrant, points, self._collection)

        # Extract first-chunk vector per event for anomaly scoring
        event_first_vector: dict[str, list[float]] = {}
        for (event, chunk_idx, _), embedding in zip(items, embeddings):
            if chunk_idx == 0:
                event_first_vector[event.id] = embedding

        try:
            query_vectors = [event_first_vector[e.id] for e in events]
            anomaly_results = await score_batch(
                events, query_vectors, self._qdrant, self._anomaly_config, self._collection
            )
            for result in anomaly_results:
                await insert_anomaly(self._pool, result)
        except Exception as exc:
            logger.warning("Anomaly scoring failed, skipping: %s", exc)

        await mark_embedded(self._pool, [e.id for e in events])
        return True
```

- [ ] **Step 4: Run all ingestion tests**

```bash
pytest tests/ingestion/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ingestion/pipeline.py tests/ingestion/test_pipeline.py
git commit -m "feat: ingestion/pipeline.py — inline anomaly scoring after upsert, errors non-fatal (TDD)"
```

---

## Task 9: `api/routes/analyze.py`

**Files:**
- Create: `api/routes/analyze.py`
- Create: `tests/api/test_analyze.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_analyze.py
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/api/test_analyze.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `api/routes/analyze.py`**

```python
# api/routes/analyze.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log, insert_rca
from intelligence.analyze import build_rca_context, create_tasks_from_rca, run_rca
from models.rca import RootCauseAnalysis
from models.task import ActionableTask

router = APIRouter()


class AnalyzeRequest(BaseModel):
    log_id: str
    create_tasks: bool = True


class AnalyzeResponse(BaseModel):
    rca: RootCauseAnalysis
    tasks: list[ActionableTask]


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_log(body: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    cfg = request.app.state.config
    try:
        context = await build_rca_context(
            log_id=body.log_id,
            pool=request.app.state.db_pool,
            openai_client=request.app.state.openai_client,
            qdrant_client=request.app.state.qdrant_client,
            config=cfg["rca"],
            collection=cfg["qdrant"].get("collection", "log_events"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        rca = await run_rca(context, request.app.state.anthropic_client, cfg["rca"])
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await insert_rca(request.app.state.db_pool, rca)
    await append_audit_log(
        request.app.state.db_pool, "rca_created", {"rca_id": rca.id, "log_id": body.log_id}
    )

    tasks: list[ActionableTask] = []
    if body.create_tasks:
        tasks = await create_tasks_from_rca(rca, request.app.state.db_pool)
        for task in tasks:
            await append_audit_log(
                request.app.state.db_pool, "task_created", {"task_id": task.id, "rca_id": rca.id}
            )

    return AnalyzeResponse(rca=rca, tasks=tasks)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_analyze.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routes/analyze.py tests/api/test_analyze.py
git commit -m "feat: POST /api/analyze route — RCA + task creation with 404/502 guards (TDD)"
```

---

## Task 10: `api/routes/correlate.py`

**Files:**
- Create: `api/routes/correlate.py`
- Create: `tests/api/test_correlate.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/api/test_correlate.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `api/routes/correlate.py`**

```python
# api/routes/correlate.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from intelligence.correlate import CorrelateResponse, correlate_trace

router = APIRouter()


@router.get("/correlate/{trace_id}", response_model=CorrelateResponse)
async def correlate(
    trace_id: str,
    request: Request,
    fresh_analysis: bool = False,
) -> CorrelateResponse:
    try:
        return await correlate_trace(
            trace_id=trace_id,
            fresh_analysis=fresh_analysis,
            pool=request.app.state.db_pool,
            openai_client=request.app.state.openai_client,
            qdrant_client=request.app.state.qdrant_client,
            anthropic_client=request.app.state.anthropic_client,
            config=request.app.state.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_correlate.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routes/correlate.py tests/api/test_correlate.py
git commit -m "feat: GET /api/correlate/{trace_id} route with fresh_analysis flag (TDD)"
```

---

## Task 11: `api/routes/anomalies.py`

**Files:**
- Create: `api/routes/anomalies.py`
- Create: `tests/api/test_anomalies.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/api/test_anomalies.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `api/routes/anomalies.py`**

```python
# api/routes/anomalies.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log, get_anomalies, mark_anomaly_reviewed
from models.anomaly import AnomalyResult

router = APIRouter()


class AnomaliesResponse(BaseModel):
    results: list[AnomalyResult]
    total: int


class ReviewResponse(BaseModel):
    anomaly: AnomalyResult


@router.get("/anomalies", response_model=AnomaliesResponse)
async def list_anomalies(
    request: Request,
    reviewed: bool | None = None,
    is_anomaly: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AnomaliesResponse:
    results, total = await get_anomalies(
        request.app.state.db_pool,
        reviewed=reviewed,
        is_anomaly=is_anomaly,
        limit=min(limit, 200),
        offset=offset,
    )
    return AnomaliesResponse(results=results, total=total)


@router.post("/anomalies/{anomaly_id}/review", response_model=ReviewResponse)
async def review_anomaly(anomaly_id: str, request: Request) -> ReviewResponse:
    anomaly = await mark_anomaly_reviewed(request.app.state.db_pool, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail=f"anomaly {anomaly_id} not found")
    await append_audit_log(
        request.app.state.db_pool, "anomaly_reviewed", {"anomaly_id": anomaly_id}
    )
    return ReviewResponse(anomaly=anomaly)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/api/test_anomalies.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routes/anomalies.py tests/api/test_anomalies.py
git commit -m "feat: GET /api/anomalies + POST /api/anomalies/{id}/review routes (TDD)"
```

---

## Task 12: `api/routes/tasks.py`

**Files:**
- Create: `api/routes/tasks.py`
- Create: `tests/api/test_tasks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_tasks.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from models.task import ActionableTask, TaskPriority, TaskStatus


def _make_task(**kwargs) -> ActionableTask:
    return ActionableTask(
        rca_id="rca-001",
        log_id="log-001",
        title="Fix pool",
        description="Increase pool size",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        **kwargs,
    )


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
    task = _make_task(status=TaskStatus.PENDING)
    approved = _make_task(status=TaskStatus.APPROVED)

    with patch("api.routes.tasks.update_task_status", return_value=approved), \
         patch("api.routes.tasks.append_audit_log"):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{task.id}/approve")

    assert resp.status_code == 200
    assert resp.json()["task"]["status"] == "approved"


@pytest.mark.asyncio
async def test_approve_task_returns_404_when_not_found(test_app):
    with patch("api.routes.tasks.get_task_by_id", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post("/api/tasks/nonexistent/approve")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_task_returns_200(test_app):
    dismissed = _make_task(status=TaskStatus.DISMISSED)
    with patch("api.routes.tasks.get_task_by_id", return_value=_make_task()), \
         patch("api.routes.tasks.update_task_status", return_value=dismissed), \
         patch("api.routes.tasks.append_audit_log"):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{dismissed.id}/dismiss")

    assert resp.status_code == 200
    assert resp.json()["task"]["status"] == "dismissed"


@pytest.mark.asyncio
async def test_dismiss_task_returns_409_when_resolved(test_app):
    resolved = _make_task(status=TaskStatus.RESOLVED)
    with patch("api.routes.tasks.get_task_by_id", return_value=resolved):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{resolved.id}/dismiss")

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approve_task_returns_409_when_already_approved(test_app):
    approved = _make_task(status=TaskStatus.APPROVED)
    with patch("api.routes.tasks.get_task_by_id", return_value=approved):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/tasks/{approved.id}/approve")

    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/api/test_tasks.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Add `get_task_by_id` to `db/postgres.py` and commit**

```python
async def get_task_by_id(pool: asyncpg.Pool, task_id: str) -> ActionableTask | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    return _row_to_task(row) if row else None
```

```bash
git add db/postgres.py
git commit -m "feat: db/postgres.py — get_task_by_id helper"
```

- [ ] **Step 4: Implement `api/routes/tasks.py`**

```python
# api/routes/tasks.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.postgres import append_audit_log, get_task_by_id, get_tasks, update_task_status
from models.task import ActionableTask, TaskStatus

router = APIRouter()

_DISMISSABLE_STATUSES = {TaskStatus.PENDING, TaskStatus.APPROVED}


class TasksResponse(BaseModel):
    results: list[ActionableTask]
    total: int


class TaskResponse(BaseModel):
    task: ActionableTask


@router.get("/tasks", response_model=TasksResponse)
async def list_tasks(
    request: Request,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> TasksResponse:
    results, total = await get_tasks(
        request.app.state.db_pool,
        status=status,
        priority=priority,
        limit=min(limit, 200),
        offset=offset,
    )
    return TasksResponse(results=results, total=total)


@router.post("/tasks/{task_id}/approve", response_model=TaskResponse)
async def approve_task(task_id: str, request: Request) -> TaskResponse:
    existing = await get_task_by_id(request.app.state.db_pool, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    if existing.status != TaskStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"cannot approve task with status '{existing.status.value}'",
        )
    task = await update_task_status(request.app.state.db_pool, task_id, TaskStatus.APPROVED.value)
    await append_audit_log(
        request.app.state.db_pool, "task_approved", {"task_id": task_id}
    )
    return TaskResponse(task=task)


@router.post("/tasks/{task_id}/dismiss", response_model=TaskResponse)
async def dismiss_task(task_id: str, request: Request) -> TaskResponse:
    existing = await get_task_by_id(request.app.state.db_pool, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    if existing.status not in _DISMISSABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"cannot dismiss task with status '{existing.status.value}'",
        )
    task = await update_task_status(request.app.state.db_pool, task_id, TaskStatus.DISMISSED.value)
    await append_audit_log(
        request.app.state.db_pool, "task_dismissed", {"task_id": task_id}
    )
    return TaskResponse(task=task)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/api/test_tasks.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add api/routes/tasks.py tests/api/test_tasks.py db/postgres.py
git commit -m "feat: GET /api/tasks + POST approve/dismiss with 404/409 guards (TDD)"
```

---

## Task 13: Wire Everything — `api/main.py` + `config.yaml`

**Files:**
- Modify: `api/main.py`
- Modify: `config.yaml`
- Modify: `tests/api/conftest.py`

- [ ] **Step 1: Update `config.yaml`**

Add to the end of `config.yaml`:

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
  fresh_analysis: false
  max_trace_logs: 200
```

- [ ] **Step 2: Update `api/main.py`**

Replace with:

```python
# api/main.py
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from anthropic import AsyncAnthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from openai import AsyncOpenAI
from prometheus_fastapi_instrumentator import Instrumentator

from api.routes.analyze import router as analyze_router
from api.routes.anomalies import router as anomalies_router
from api.routes.correlate import router as correlate_router
from api.routes.health import router as health_router
from api.routes.search import router as search_router
from api.routes.tasks import router as tasks_router
from db.postgres import init_pool
from db.qdrant import ensure_collection, init_qdrant
from ingestion.pipeline import IngestionWorker
from sync.engine import SyncEngine

_config: dict = yaml.safe_load(
    (Path(__file__).parent.parent / "config.yaml").read_text()
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = _config
    app.state.db_pool = await init_pool(dsn=_config["database"]["url"])

    qdrant_cfg = _config["qdrant"]
    app.state.qdrant_client = await init_qdrant(
        host=qdrant_cfg["host"], port=qdrant_cfg["port"]
    )
    await ensure_collection(app.state.qdrant_client, qdrant_cfg.get("collection", "log_events"))

    app.state.openai_client = AsyncOpenAI()
    app.state.anthropic_client = AsyncAnthropic()

    engine = SyncEngine(config=_config, pool=app.state.db_pool)
    await engine.start()

    ingestion_worker = IngestionWorker(
        pool=app.state.db_pool,
        openai_client=app.state.openai_client,
        qdrant_client=app.state.qdrant_client,
        batch_size=_config["ingestion"].get("batch_size", 100),
        collection=qdrant_cfg.get("collection", "log_events"),
        anomaly_config=_config.get("anomaly", {}),
    )
    await ingestion_worker.start()

    yield

    await ingestion_worker.stop()
    await engine.stop()
    await app.state.db_pool.close()


app = FastAPI(title="LogIQ", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.include_router(health_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(correlate_router, prefix="/api")
app.include_router(anomalies_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
```

- [ ] **Step 3: Update `tests/api/conftest.py`**

```python
# tests/api/conftest.py
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_lifespan_deps(monkeypatch):
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()
    mock_qdrant = MagicMock()

    monkeypatch.setattr("api.main.init_pool", AsyncMock(return_value=mock_pool))
    monkeypatch.setattr("api.main.init_qdrant", AsyncMock(return_value=mock_qdrant))
    monkeypatch.setattr("api.main.ensure_collection", AsyncMock())
    monkeypatch.setattr("sync.engine.SyncEngine.start", AsyncMock())
    monkeypatch.setattr("sync.engine.SyncEngine.stop", AsyncMock())
    monkeypatch.setattr("ingestion.pipeline.IngestionWorker.start", AsyncMock())
    monkeypatch.setattr("ingestion.pipeline.IngestionWorker.stop", AsyncMock())
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass. If any fail, check import paths — the most common issue is a module not yet imported in `api/main.py`.

- [ ] **Step 5: Commit**

```bash
git add api/main.py config.yaml tests/api/conftest.py
git commit -m "feat: wire analyze, correlate, anomalies, tasks routers into main + config.yaml (TDD)"
```

---

## Final Verification

- [ ] Run full suite one last time:

```bash
pytest -v --tb=short
```

All tests should pass. Green across the board.
