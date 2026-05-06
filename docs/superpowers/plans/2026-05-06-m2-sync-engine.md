# LogIQ M2 — Sync Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the background sync loop that continuously ingests log events from Loki into PostgreSQL, with cursor tracking, exponential backoff, and FastAPI lifespan wiring.

**Architecture:** `SyncEngine` coordinator reads config and spawns one `SourceWorker` per source. Each worker runs as an asyncio task — poll mode calls `fetch_logs` on a configurable interval; stream mode tails via WebSocket. Both write to the `logs` PostgreSQL table with `ON CONFLICT (id) DO NOTHING`. Cursor state in `sync_cursors` table survives restarts. `LokiAdapter.normalise()` switches from UUID4 to deterministic UUID5 so dedup is identity-based.

**Tech Stack:** Python 3.12, asyncpg 0.29.0, asyncio, FastAPI lifespan, pyyaml (already installed), pytest/pytest-asyncio/pytest-mock (already installed).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Add asyncpg==0.29.0 |
| `db/migrations/001_init.sql` | Create | `logs` + `sync_cursors` DDL |
| `db/postgres.py` | Create | asyncpg pool factory + 4 DB functions |
| `adapters/loki.py` | Modify | Deterministic UUID5 in `normalise()` |
| `sync/engine.py` | Create | `SourceWorker` + `SyncEngine` |
| `api/main.py` | Modify | Lifespan hook + config load |
| `tests/db/__init__.py` | Create | Test package |
| `tests/db/test_postgres.py` | Create | Unit tests for db/postgres.py |
| `tests/sync/__init__.py` | Create | Test package |
| `tests/sync/test_engine.py` | Create | Unit tests for sync/engine.py |
| `tests/api/conftest.py` | Create | Mock lifespan deps for API tests |

---

## Task 1: Add asyncpg and create test package init files

**Files:**
- Modify: `requirements.txt`
- Create: `tests/db/__init__.py`
- Create: `tests/sync/__init__.py`

- [ ] **Step 1: Add asyncpg to requirements.txt**

Open `requirements.txt` and add one line after `websockets==12.0`:

```
asyncpg==0.29.0
```

- [ ] **Step 2: Install it**

```bash
pip install asyncpg==0.29.0
```

Expected: `Successfully installed asyncpg-0.29.0`

- [ ] **Step 3: Verify import**

```bash
python -c "import asyncpg; print(asyncpg.__version__)"
```

Expected: `0.29.0`

- [ ] **Step 4: Create test package init files**

Create `tests/db/__init__.py` — empty file.
Create `tests/sync/__init__.py` — empty file.

```bash
touch tests/db/__init__.py tests/sync/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/db/__init__.py tests/sync/__init__.py
git commit -m "chore: add asyncpg dependency and test package init files"
```

---

## Task 2: Database migration SQL

**Files:**
- Create: `db/migrations/001_init.sql`

- [ ] **Step 1: Create the migration file**

Create `db/migrations/001_init.sql` with this exact content:

```sql
CREATE TABLE IF NOT EXISTS sync_cursors (
    source_name    TEXT        PRIMARY KEY,
    last_synced_at TIMESTAMPTZ NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logs (
    id          TEXT        PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    severity    TEXT        NOT NULL,
    service     TEXT        NOT NULL,
    environment TEXT        NOT NULL,
    trace_id    TEXT,
    span_id     TEXT,
    message     TEXT        NOT NULL,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    raw         JSONB       NOT NULL DEFAULT '{}',
    source      TEXT        NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_service   ON logs (service);
CREATE INDEX IF NOT EXISTS idx_logs_severity  ON logs (severity);
CREATE INDEX IF NOT EXISTS idx_logs_trace_id  ON logs (trace_id);
```

- [ ] **Step 2: Commit**

```bash
git add db/migrations/001_init.sql
git commit -m "feat: add 001_init.sql migration for logs and sync_cursors tables"
```

---

## Task 3: `db/postgres.py` — `init_pool`

**Files:**
- Create: `db/postgres.py`
- Create: `tests/db/test_postgres.py`

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_postgres.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.postgres import init_pool


def _make_mock_pool():
    """Return (pool_mock, conn_mock) with acquire() wired as async context manager."""
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool, conn


@pytest.mark.asyncio
async def test_init_pool_creates_pool_and_runs_migration(monkeypatch):
    mock_pool, mock_conn = _make_mock_pool()

    async def fake_create_pool(dsn):
        return mock_pool

    monkeypatch.setattr("asyncpg.create_pool", fake_create_pool)

    result = await init_pool("postgresql://test/db")

    assert result is mock_pool
    mock_conn.execute.assert_called_once()
    sql_arg = mock_conn.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS sync_cursors" in sql_arg
    assert "CREATE TABLE IF NOT EXISTS logs" in sql_arg
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/db/test_postgres.py::test_init_pool_creates_pool_and_runs_migration -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `db.postgres` does not exist yet.

- [ ] **Step 3: Create `db/postgres.py` with `init_pool`**

```python
from __future__ import annotations

from pathlib import Path

import asyncpg

from models.log_event import LogEvent

_MIGRATION_SQL = (Path(__file__).parent / "migrations" / "001_init.sql").read_text()


async def init_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        await conn.execute(_MIGRATION_SQL)
    return pool
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/db/test_postgres.py::test_init_pool_creates_pool_and_runs_migration -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add db/postgres.py tests/db/test_postgres.py
git commit -m "feat: db/postgres.py init_pool — create asyncpg pool and run migration (TDD)"
```

---

## Task 4: `db/postgres.py` — `get_cursor` and `upsert_cursor`

**Files:**
- Modify: `db/postgres.py`
- Modify: `tests/db/test_postgres.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/db/test_postgres.py`:

```python
from db.postgres import get_cursor, upsert_cursor


@pytest.mark.asyncio
async def test_get_cursor_returns_none_when_no_row():
    mock_pool, mock_conn = _make_mock_pool()
    mock_conn.fetchrow.return_value = None

    result = await get_cursor(mock_pool, "loki")

    assert result is None
    mock_conn.fetchrow.assert_called_once_with(
        "SELECT last_synced_at FROM sync_cursors WHERE source_name = $1",
        "loki",
    )


@pytest.mark.asyncio
async def test_get_cursor_returns_datetime_when_row_exists():
    mock_pool, mock_conn = _make_mock_pool()
    ts = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)
    mock_conn.fetchrow.return_value = {"last_synced_at": ts}

    result = await get_cursor(mock_pool, "loki")

    assert result == ts


@pytest.mark.asyncio
async def test_upsert_cursor_executes_insert_on_conflict():
    mock_pool, mock_conn = _make_mock_pool()
    ts = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

    await upsert_cursor(mock_pool, "loki", ts)

    mock_conn.execute.assert_called_once()
    sql, source_arg, ts_arg = mock_conn.execute.call_args[0]
    assert "INSERT INTO sync_cursors" in sql
    assert "ON CONFLICT" in sql
    assert source_arg == "loki"
    assert ts_arg == ts
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/db/test_postgres.py -k "cursor" -v
```

Expected: `ImportError` — `get_cursor` and `upsert_cursor` not defined yet.

- [ ] **Step 3: Add `get_cursor` and `upsert_cursor` to `db/postgres.py`**

Append to the existing `db/postgres.py` (after `init_pool`):

```python
from datetime import datetime


async def get_cursor(pool: asyncpg.Pool, source_name: str) -> datetime | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_synced_at FROM sync_cursors WHERE source_name = $1",
            source_name,
        )
    return row["last_synced_at"] if row else None


async def upsert_cursor(pool: asyncpg.Pool, source_name: str, ts: datetime) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sync_cursors (source_name, last_synced_at, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (source_name)
            DO UPDATE SET last_synced_at = EXCLUDED.last_synced_at,
                          updated_at = NOW()
            """,
            source_name,
            ts,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/db/test_postgres.py -k "cursor" -v
```

Expected: 3 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add db/postgres.py tests/db/test_postgres.py
git commit -m "feat: db/postgres.py get_cursor and upsert_cursor (TDD)"
```

---

## Task 5: `db/postgres.py` — `insert_logs`

**Files:**
- Modify: `db/postgres.py`
- Modify: `tests/db/test_postgres.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/db/test_postgres.py`:

```python
from models.log_event import LogEvent, SeverityLevel
from db.postgres import insert_logs


def _make_event(**kwargs) -> LogEvent:
    defaults = dict(
        id="test-id-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="connection pool exhausted",
        source="loki",
    )
    return LogEvent(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_insert_logs_calls_executemany_with_correct_columns():
    mock_pool, mock_conn = _make_mock_pool()
    event = _make_event()

    count = await insert_logs(mock_pool, [event])

    mock_conn.executemany.assert_called_once()
    sql, records = mock_conn.executemany.call_args[0]
    assert "INSERT INTO logs" in sql
    assert "ON CONFLICT (id) DO NOTHING" in sql
    assert len(records) == 1
    row = records[0]
    assert row[0] == "test-id-001"
    assert row[2] == "ERROR"
    assert row[3] == "auth-service"
    assert count == 1


@pytest.mark.asyncio
async def test_insert_logs_returns_zero_for_empty_list():
    mock_pool, mock_conn = _make_mock_pool()

    count = await insert_logs(mock_pool, [])

    mock_conn.executemany.assert_not_called()
    assert count == 0


@pytest.mark.asyncio
async def test_insert_logs_passes_all_events_as_records():
    mock_pool, mock_conn = _make_mock_pool()
    events = [_make_event(id=f"id-{i}", message=f"msg-{i}") for i in range(3)]

    count = await insert_logs(mock_pool, events)

    _, records = mock_conn.executemany.call_args[0]
    assert len(records) == 3
    assert count == 3
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/db/test_postgres.py -k "insert" -v
```

Expected: `ImportError` — `insert_logs` not defined yet.

- [ ] **Step 3: Add `insert_logs` to `db/postgres.py`**

Append to `db/postgres.py`:

```python
async def insert_logs(pool: asyncpg.Pool, events: list[LogEvent]) -> int:
    if not events:
        return 0
    records = [
        (
            e.id,
            e.timestamp,
            e.severity.value,
            e.service,
            e.environment,
            e.trace_id,
            e.span_id,
            e.message,
            dict(e.metadata),
            dict(e.raw),
            e.source,
        )
        for e in events
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO logs
                (id, timestamp, severity, service, environment,
                 trace_id, span_id, message, metadata, raw, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (id) DO NOTHING
            """,
            records,
        )
    return len(events)
```

- [ ] **Step 4: Run all db tests**

```bash
pytest tests/db/test_postgres.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add db/postgres.py tests/db/test_postgres.py
git commit -m "feat: db/postgres.py insert_logs with ON CONFLICT dedup (TDD)"
```

---

## Task 6: `adapters/loki.py` — deterministic UUID5 in `normalise()`

**Files:**
- Modify: `adapters/loki.py`
- Modify: `tests/adapters/test_loki.py`

- [ ] **Step 1: Write the failing test**

Open `tests/adapters/test_loki.py` and append this test:

```python
def test_normalise_produces_deterministic_id():
    adapter = LokiAdapter(url="http://loki:3100")
    raw = {
        "timestamp": "2026-05-06T10:00:00+00:00",
        "severity": "ERROR",
        "service": "auth-service",
        "environment": "production",
        "message": "connection pool exhausted",
        "metadata": {},
    }
    event1 = adapter.normalise(raw)
    event2 = adapter.normalise(raw)
    assert event1.id == event2.id


def test_normalise_produces_different_ids_for_different_messages():
    adapter = LokiAdapter(url="http://loki:3100")
    raw_a = {
        "timestamp": "2026-05-06T10:00:00+00:00",
        "severity": "ERROR",
        "service": "svc",
        "environment": "production",
        "message": "error A",
        "metadata": {},
    }
    raw_b = {**raw_a, "message": "error B"}
    assert adapter.normalise(raw_a).id != adapter.normalise(raw_b).id
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/adapters/test_loki.py -k "deterministic" -v
```

Expected: both tests `FAIL` — current `normalise()` uses `uuid.uuid4()` so IDs are random.

- [ ] **Step 3: Add `_dedup_id` and update `normalise()` in `adapters/loki.py`**

Add this near the top of `adapters/loki.py`, after the existing imports:

```python
import uuid

_LOGIQ_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _dedup_id(source: str, timestamp: str, message: str) -> str:
    return str(uuid.uuid5(_LOGIQ_NS, f"{source}:{timestamp}:{message}"))
```

Replace the entire `normalise()` method with:

```python
def normalise(self, raw: dict) -> LogEvent:
    severity_str = raw.get("severity", "UNKNOWN").upper()
    try:
        severity = SeverityLevel(severity_str)
    except ValueError:
        severity = SeverityLevel.UNKNOWN

    ts_str = raw.get("timestamp", "")
    return LogEvent(
        id=_dedup_id(self._name, ts_str, raw.get("message", "")),
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        severity=severity,
        service=raw.get("service", "unknown"),
        environment=raw.get("environment", "unknown"),
        trace_id=raw.get("trace_id"),
        span_id=raw.get("span_id"),
        message=raw["message"],
        metadata=raw.get("metadata", {}),
        raw=raw,
        source=self._name,
    )
```

- [ ] **Step 4: Run all loki adapter tests**

```bash
pytest tests/adapters/test_loki.py -v
```

Expected: all tests `PASSED` — existing tests still pass, new determinism tests pass.

- [ ] **Step 5: Commit**

```bash
git add adapters/loki.py tests/adapters/test_loki.py
git commit -m "feat: LokiAdapter.normalise() uses deterministic UUID5 for dedup (TDD)"
```

---

## Task 7: `sync/engine.py` — `SourceWorker` poll mode and backoff

**Files:**
- Create: `sync/engine.py`
- Create: `tests/sync/test_engine.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sync/test_engine.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from models.log_event import LogEvent, SeverityLevel
from sync.engine import SourceWorker


def _make_event(n: int = 0) -> LogEvent:
    return LogEvent(
        id=f"evt-{n}",
        timestamp=datetime(2026, 5, 6, 10, 0, n, tzinfo=timezone.utc),
        severity=SeverityLevel.INFO,
        service="svc",
        environment="production",
        message=f"msg-{n}",
        source="loki",
    )


def _make_adapter(events: list[LogEvent] | None = None) -> MagicMock:
    adapter = MagicMock()
    adapter.get_source_name.return_value = "loki"
    adapter.fetch_logs = AsyncMock(return_value=events or [])
    return adapter


def _make_pool() -> MagicMock:
    return MagicMock()


# ── _poll_once ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_once_fetches_with_cursor_when_cursor_exists():
    ts = datetime(2026, 5, 6, 9, 0, 0, tzinfo=timezone.utc)
    adapter = _make_adapter([_make_event()])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=ts)), \
         patch("sync.engine.db.insert_logs", AsyncMock()) as mock_insert, \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        await worker._poll_once()

    adapter.fetch_logs.assert_called_once()
    call_kwargs = adapter.fetch_logs.call_args
    assert call_kwargs.kwargs["start"] == ts
    mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_poll_once_defaults_start_when_no_cursor():
    adapter = _make_adapter([])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll", poll_interval=30)
        before = datetime.now(tz=timezone.utc)
        await worker._poll_once()
        after = datetime.now(tz=timezone.utc)

    start_arg = adapter.fetch_logs.call_args.kwargs["start"]
    expected_start = before - timedelta(seconds=30)
    assert abs((start_arg - expected_start).total_seconds()) < 1.0


@pytest.mark.asyncio
async def test_poll_once_skips_insert_when_no_events():
    adapter = _make_adapter([])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()) as mock_insert, \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        await worker._poll_once()

    mock_insert.assert_not_called()


@pytest.mark.asyncio
async def test_poll_once_always_upserts_cursor():
    adapter = _make_adapter([])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()) as mock_upsert:
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        await worker._poll_once()

    mock_upsert.assert_called_once()
    source_arg = mock_upsert.call_args[0][1]
    assert source_arg == "loki"


# ── backoff ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backoff_doubles_on_consecutive_failures():
    adapter = _make_adapter()
    adapter.fetch_logs.side_effect = RuntimeError("loki down")
    pool = _make_pool()

    sleep_calls = []

    async def fake_sleep(n):
        sleep_calls.append(n)
        if len(sleep_calls) >= 3:
            raise asyncio.CancelledError

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        with pytest.raises(asyncio.CancelledError):
            await worker._poll_loop()

    assert sleep_calls[0] == 1.0
    assert sleep_calls[1] == 2.0


@pytest.mark.asyncio
async def test_backoff_resets_on_success():
    adapter = _make_adapter([])
    pool = _make_pool()
    call_count = 0

    async def flaky_fetch(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient error")
        if call_count == 3:
            raise asyncio.CancelledError
        return []

    adapter.fetch_logs.side_effect = flaky_fetch

    sleep_calls = []

    async def fake_sleep(n):
        sleep_calls.append(n)

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll", poll_interval=30)
        with pytest.raises(asyncio.CancelledError):
            await worker._poll_loop()

    # First sleep is backoff (1.0), second sleep is normal poll interval (30)
    assert sleep_calls[0] == 1.0
    assert sleep_calls[1] == 30
```

Add `import asyncio` at the top of the test file.

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/sync/test_engine.py -v
```

Expected: `ImportError` — `sync.engine` does not exist yet.

- [ ] **Step 3: Create `sync/engine.py`**

```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from adapters.base import BaseSourceAdapter
from adapters.loki import LokiAdapter
from db import postgres as db
from models.log_event import LogEvent

logger = logging.getLogger(__name__)

_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_MAX_FAILURES_BEFORE_CRITICAL = 10


class SourceWorker:
    def __init__(
        self,
        adapter: BaseSourceAdapter,
        pool: Any,
        mode: str,
        poll_interval: int = 30,
        stream_batch_size: int = 100,
        stream_flush_interval: float = 5.0,
    ) -> None:
        self._adapter = adapter
        self._pool = pool
        self._mode = mode
        self._poll_interval = poll_interval
        self._stream_batch_size = stream_batch_size
        self._stream_flush_interval = stream_flush_interval
        self._task: asyncio.Task | None = None
        self._backoff = _BASE_BACKOFF
        self._consecutive_failures = 0

    async def start(self) -> None:
        if self._mode == "poll":
            self._task = asyncio.create_task(self._poll_loop())
        else:
            self._task = asyncio.create_task(self._stream_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── poll ──────────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
                self._reset_backoff()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._on_failure(exc)
                await asyncio.sleep(self._backoff)
                self._advance_backoff()
                continue
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        source = self._adapter.get_source_name()
        now = datetime.now(tz=timezone.utc)
        cursor = await db.get_cursor(self._pool, source)
        start = cursor if cursor is not None else now - timedelta(seconds=self._poll_interval)
        events = await self._adapter.fetch_logs(start=start, end=now)
        if events:
            await db.insert_logs(self._pool, events)
        await db.upsert_cursor(self._pool, source, now)

    # ── stream ────────────────────────────────────────────────────────────────

    async def _stream_loop(self) -> None:
        while True:
            try:
                await self._stream_once()
                self._reset_backoff()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._on_failure(exc)
                await asyncio.sleep(self._backoff)
                self._advance_backoff()

    async def _stream_once(self) -> None:
        buffer: list[LogEvent] = []
        aiter = self._adapter.stream_logs().__aiter__()
        while True:
            try:
                event = await asyncio.wait_for(
                    aiter.__anext__(), timeout=self._stream_flush_interval
                )
                buffer.append(event)
                if len(buffer) >= self._stream_batch_size:
                    await db.insert_logs(self._pool, buffer)
                    buffer.clear()
            except asyncio.TimeoutError:
                if buffer:
                    await db.insert_logs(self._pool, buffer)
                    buffer.clear()
            except StopAsyncIteration:
                if buffer:
                    await db.insert_logs(self._pool, buffer)
                return

    # ── backoff ───────────────────────────────────────────────────────────────

    def _on_failure(self, exc: Exception) -> None:
        self._consecutive_failures += 1
        level = (
            logging.CRITICAL
            if self._consecutive_failures >= _MAX_FAILURES_BEFORE_CRITICAL
            else logging.WARNING
        )
        logger.log(
            level,
            "Source %s: failure #%d, retry in %.1fs — %s",
            self._adapter.get_source_name(),
            self._consecutive_failures,
            self._backoff,
            exc,
        )

    def _reset_backoff(self) -> None:
        self._backoff = _BASE_BACKOFF
        self._consecutive_failures = 0

    def _advance_backoff(self) -> None:
        self._backoff = min(self._backoff * 2, _MAX_BACKOFF)


class SyncEngine:
    def __init__(self, config: dict, pool: Any) -> None:
        self._workers: list[SourceWorker] = [
            SourceWorker(
                adapter=_make_adapter(src),
                pool=pool,
                mode=src.get("mode", "poll"),
                poll_interval=src.get("poll_interval_seconds", 30),
            )
            for src in config.get("sources", [])
        ]

    async def start(self) -> None:
        for worker in self._workers:
            await worker.start()

    async def stop(self) -> None:
        for worker in self._workers:
            await worker.stop()


def _make_adapter(source_cfg: dict) -> BaseSourceAdapter:
    source_type = source_cfg["type"]
    if source_type == "loki":
        return LokiAdapter(url=source_cfg["url"], name=source_cfg["name"])
    raise ValueError(f"Unknown source type: {source_type!r}")
```

- [ ] **Step 4: Run poll + backoff tests**

```bash
pytest tests/sync/test_engine.py -k "poll or backoff" -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add sync/engine.py tests/sync/test_engine.py
git commit -m "feat: SourceWorker poll mode with exponential backoff (TDD)"
```

---

## Task 8: `sync/engine.py` — `SourceWorker` stream mode

**Files:**
- Modify: `tests/sync/test_engine.py`

(No changes to `sync/engine.py` — stream code is already in the file from Task 7.)

- [ ] **Step 1: Write the failing stream tests**

Append to `tests/sync/test_engine.py`:

```python
# ── stream mode ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_worker_flushes_at_batch_size():
    pool = _make_pool()
    events = [_make_event(i) for i in range(5)]
    idx = 0

    async def fake_stream():
        nonlocal idx
        for e in events:
            yield e

    adapter = _make_adapter()
    adapter.stream_logs.return_value = fake_stream()

    with patch("sync.engine.db.insert_logs", AsyncMock()) as mock_insert:
        worker = SourceWorker(
            adapter=adapter,
            pool=pool,
            mode="stream",
            stream_batch_size=3,
            stream_flush_interval=5.0,
        )
        await worker._stream_once()

    # 5 events with batch_size=3: first flush at 3 events, second flush with 2
    assert mock_insert.call_count == 2
    first_batch = mock_insert.call_args_list[0][0][1]
    second_batch = mock_insert.call_args_list[1][0][1]
    assert len(first_batch) == 3
    assert len(second_batch) == 2


@pytest.mark.asyncio
async def test_stream_worker_flushes_on_timeout():
    pool = _make_pool()
    event = _make_event()
    flushed = asyncio.Event()

    async def mock_insert(p, evts):
        flushed.set()

    async def trickle():
        yield event
        await asyncio.sleep(10)  # longer than flush_interval — triggers timeout

    adapter = _make_adapter()
    adapter.stream_logs.return_value = trickle()

    with patch("sync.engine.db.insert_logs", side_effect=mock_insert):
        worker = SourceWorker(
            adapter=adapter,
            pool=pool,
            mode="stream",
            stream_batch_size=100,
            stream_flush_interval=0.05,
        )
        task = asyncio.create_task(worker._stream_once())
        await asyncio.wait_for(flushed.wait(), timeout=2.0)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    assert flushed.is_set()


@pytest.mark.asyncio
async def test_stream_worker_start_creates_stream_task():
    pool = _make_pool()
    adapter = _make_adapter()

    async def infinite_stream():
        while True:
            await asyncio.sleep(1)
            yield _make_event()

    adapter.stream_logs.return_value = infinite_stream()

    with patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="stream")
        await worker.start()
        assert worker._task is not None
        assert not worker._task.done()
        await worker.stop()
        assert worker._task.cancelled() or worker._task.done()
```

- [ ] **Step 2: Run stream tests**

```bash
pytest tests/sync/test_engine.py -k "stream" -v
```

Expected: all 3 tests `PASSED` — stream code was already written in Task 7.

- [ ] **Step 3: Commit**

```bash
git add tests/sync/test_engine.py
git commit -m "test: SourceWorker stream mode — batch flush and timeout flush (TDD)"
```

---

## Task 9: `sync/engine.py` — `SyncEngine` coordinator

**Files:**
- Modify: `tests/sync/test_engine.py`

(No changes to `sync/engine.py` — `SyncEngine` is already written.)

- [ ] **Step 1: Write the failing SyncEngine tests**

Append to `tests/sync/test_engine.py`:

```python
from sync.engine import SyncEngine


# ── SyncEngine ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_engine_creates_one_worker_per_source():
    config = {
        "sources": [
            {"name": "loki", "type": "loki", "url": "http://loki:3100", "mode": "poll", "poll_interval_seconds": 30},
            {"name": "loki2", "type": "loki", "url": "http://loki2:3100", "mode": "stream", "poll_interval_seconds": 30},
        ]
    }
    pool = _make_pool()

    with patch("sync.engine.LokiAdapter") as mock_loki_cls:
        mock_loki_cls.return_value = _make_adapter()
        engine = SyncEngine(config=config, pool=pool)

    assert len(engine._workers) == 2


@pytest.mark.asyncio
async def test_sync_engine_start_starts_all_workers():
    config = {
        "sources": [
            {"name": "loki", "type": "loki", "url": "http://loki:3100", "mode": "poll", "poll_interval_seconds": 30},
        ]
    }
    pool = _make_pool()

    with patch("sync.engine.LokiAdapter") as mock_loki_cls, \
         patch.object(SourceWorker, "start", new_callable=AsyncMock) as mock_start, \
         patch.object(SourceWorker, "stop", new_callable=AsyncMock):
        mock_loki_cls.return_value = _make_adapter()
        engine = SyncEngine(config=config, pool=pool)
        await engine.start()

    mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_sync_engine_stop_stops_all_workers():
    config = {
        "sources": [
            {"name": "loki", "type": "loki", "url": "http://loki:3100", "mode": "poll", "poll_interval_seconds": 30},
            {"name": "loki2", "type": "loki", "url": "http://loki2:3100", "mode": "poll", "poll_interval_seconds": 30},
        ]
    }
    pool = _make_pool()

    with patch("sync.engine.LokiAdapter") as mock_loki_cls, \
         patch.object(SourceWorker, "start", new_callable=AsyncMock), \
         patch.object(SourceWorker, "stop", new_callable=AsyncMock) as mock_stop:
        mock_loki_cls.return_value = _make_adapter()
        engine = SyncEngine(config=config, pool=pool)
        await engine.start()
        await engine.stop()

    assert mock_stop.call_count == 2


def test_make_adapter_raises_for_unknown_type():
    from sync.engine import _make_adapter
    with pytest.raises(ValueError, match="Unknown source type"):
        _make_adapter({"type": "splunk", "url": "http://splunk", "name": "s"})
```

Add `from unittest.mock import patch` to the imports if not already there (it is from Task 7).

- [ ] **Step 2: Run SyncEngine tests**

```bash
pytest tests/sync/test_engine.py -k "sync_engine or make_adapter" -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 3: Run the full sync test suite**

```bash
pytest tests/sync/test_engine.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 4: Commit**

```bash
git add tests/sync/test_engine.py
git commit -m "test: SyncEngine coordinator — start/stop all workers (TDD)"
```

---

## Task 10: `api/main.py` — lifespan integration

**Files:**
- Modify: `api/main.py`
- Create: `tests/api/conftest.py`

- [ ] **Step 1: Create `tests/api/conftest.py` to mock lifespan deps**

This prevents health tests from trying to connect to a real PostgreSQL server.

```python
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_lifespan_deps(monkeypatch):
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()

    monkeypatch.setattr("db.postgres.init_pool", AsyncMock(return_value=mock_pool))
    monkeypatch.setattr("sync.engine.SyncEngine.start", AsyncMock())
    monkeypatch.setattr("sync.engine.SyncEngine.stop", AsyncMock())
```

- [ ] **Step 2: Run existing health tests to confirm they still pass with the fixture**

```bash
pytest tests/api/test_health.py -v
```

Expected: all existing health tests still `PASSED`.

- [ ] **Step 3: Update `api/main.py` to add lifespan**

Replace the entire contents of `api/main.py` with:

```python
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_fastapi_instrumentator import Instrumentator

from api.routes.health import router as health_router
from db.postgres import init_pool
from sync.engine import SyncEngine

_config: dict = yaml.safe_load(
    (Path(__file__).parent.parent / "config.yaml").read_text()
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await init_pool(dsn=_config["database"]["url"])
    engine = SyncEngine(config=_config, pool=app.state.db_pool)
    await engine.start()
    yield
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
```

- [ ] **Step 4: Run health tests to confirm they pass after the change**

```bash
pytest tests/api/test_health.py -v
```

Expected: all health tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/api/conftest.py
git commit -m "feat: api/main.py lifespan — init DB pool and start SyncEngine on startup"
```

---

## Task 11: Final verification

**Files:** none changed

- [ ] **Step 1: Run the complete test suite**

```bash
pytest -v
```

Expected: all tests `PASSED`. Approximate count: ~59 (M1) + 9 (db/postgres) + 13 (sync/engine) + 2 (loki deterministic id) = ~83 passed.

- [ ] **Step 2: Verify no circular imports**

```bash
python -c "
from db.postgres import init_pool
from sync.engine import SyncEngine, SourceWorker
from api.main import app
print('no circular imports')
"
```

Expected: `no circular imports`

- [ ] **Step 3: Verify config loads cleanly**

```bash
python -c "
from pathlib import Path
import yaml
cfg = yaml.safe_load(Path('config.yaml').read_text())
assert 'sources' in cfg
assert 'database' in cfg
print('config OK:', len(cfg['sources']), 'source(s) configured')
"
```

Expected: `config OK: 1 source(s) configured`

- [ ] **Step 4: Commit final verification**

```bash
git commit --allow-empty -m "chore: M2 Sync Engine complete — all tests passing"
```

---

## Definition of Done

- [ ] `pytest -v` passes with ~83+ tests, zero failures
- [ ] `python -c "from sync.engine import SyncEngine; print('OK')"` succeeds
- [ ] `python -c "from api.main import app; print('OK')"` succeeds
- [ ] `db/migrations/001_init.sql` creates `logs` and `sync_cursors` tables
- [ ] `LokiAdapter.normalise()` produces identical UUIDs for identical inputs
- [ ] `SourceWorker` in poll mode reads cursor → fetches → inserts → advances cursor
- [ ] `SourceWorker` in stream mode flushes at batch 100 or 5s timeout
- [ ] Backoff doubles on failure, resets on success
- [ ] FastAPI lifespan starts `SyncEngine` on startup and stops it on shutdown
