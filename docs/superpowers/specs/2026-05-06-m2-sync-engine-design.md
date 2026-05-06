# LogIQ M2 — Sync Engine Design

**Date:** 2026-05-06
**Milestone:** M2 — Sync Engine
**Status:** Approved
**Scope:** PostgreSQL schema + asyncpg layer + SyncEngine/SourceWorker + FastAPI lifespan wiring

---

## 1. Objective

Build the background sync loop that continuously ingests log events from configured sources
into PostgreSQL. M2 is the first milestone with real external side effects: it writes to the
`logs` and `sync_cursors` tables and starts as an asyncio task alongside the FastAPI app.

M1 (models + LokiAdapter) is a pure library layer; M2 consumes it. M3 (Ingestion Pipeline)
will add embedding + Qdrant + anomaly scoring on top of the `logs` table written here.

---

## 2. Architecture

### 2.1 Components

```
sync/
  engine.py         — SyncEngine (coordinator) + SourceWorker (per-source asyncio task)

db/
  postgres.py       — asyncpg pool factory + insert_logs / get_cursor / upsert_cursor
  migrations/
    001_init.sql    — logs + sync_cursors tables and indexes

api/main.py         — @asynccontextmanager lifespan: init pool → start engine → yield → stop
adapters/loki.py    — normalise() uses deterministic UUID5 instead of UUID4
requirements.txt    — add asyncpg==0.29.0
```

**SyncEngine** reads `config.yaml`, instantiates one `SourceWorker` per configured source,
and calls `start()` / `stop()` on each. It owns no DB calls and no adapter logic.

**SourceWorker** owns everything for one source: its asyncio task, cursor state, backoff
counter, and adapter instance. It reads/writes `db.postgres` functions directly.
Mode (poll vs stream) is set by the source config entry.

### 2.2 Data Flow

**Poll mode** (default, `poll_interval_seconds: 30`):

```
SourceWorker wakes
  → get_cursor(source_name)               # None on first run
  → start = cursor ?? (now - interval)
  → adapter.fetch_logs(start, end=now)
  → insert_logs(pool, batch)              # ON CONFLICT (id) DO NOTHING
  → upsert_cursor(source_name, now)
  → asyncio.sleep(poll_interval_seconds)
  → repeat
```

**Stream mode** (`mode: stream`):

```
SourceWorker starts persistent WebSocket loop
  → adapter.stream_logs()
  → buffer events
  → flush when: len(buffer) >= 100  OR  5 s elapsed
  → insert_logs(pool, buffer)             # ON CONFLICT (id) DO NOTHING
  → on disconnect: exponential backoff, reconnect
```

Stream mode does not update `sync_cursors` — the tail is real-time with no gap to replay.

### 2.3 Backoff

Applies to both modes on any exception from the adapter or DB:

- Delays: 1 s → 2 s → 4 s → 8 s → … → 60 s (cap)
- Resets to 1 s on next successful operation
- Logged at WARNING each retry; CRITICAL after 10 consecutive failures (keeps retrying)

---

## 3. Database Schema (`db/migrations/001_init.sql`)

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

Migration is run automatically on pool init via `init_pool()`.

---

## 4. `db/postgres.py` Interface

```python
async def init_pool(dsn: str) -> asyncpg.Pool:
    """Create pool and run 001_init.sql migration."""

async def insert_logs(pool: asyncpg.Pool, events: list[LogEvent]) -> int:
    """Batch-insert events. Returns count of rows actually inserted (dedup via ON CONFLICT)."""

async def get_cursor(pool: asyncpg.Pool, source_name: str) -> datetime | None:
    """Return last_synced_at for source, or None if no cursor exists."""

async def upsert_cursor(pool: asyncpg.Pool, source_name: str, ts: datetime) -> None:
    """Insert or update last_synced_at for source."""
```

The pool is created once at FastAPI startup and stored on `app.state.db_pool`.

---

## 5. Deterministic Deduplication ID

`LokiAdapter.normalise()` changes `id` from `uuid.uuid4()` to:

```python
import uuid, hashlib

LOGIQ_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL

def _dedup_id(source: str, timestamp_ns: int, message: str) -> str:
    key = f"{source}:{timestamp_ns}:{message}"
    return str(uuid.uuid5(LOGIQ_NS, key))
```

Same raw event always maps to the same UUID5, making `ON CONFLICT DO NOTHING` sufficient
for deduplication with no extra query.

---

## 6. FastAPI Lifespan Integration (`api/main.py`)

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await init_pool(dsn=config["database"]["url"])
    engine = SyncEngine(config=config, pool=app.state.db_pool)
    await engine.start()
    yield
    await engine.stop()
    await app.state.db_pool.close()

app = FastAPI(title="LogIQ", version="0.1.0", lifespan=lifespan)
```

Config is loaded once from `config.yaml` at module level.

---

## 7. Testing Strategy

All tests run without a live Postgres or Loki — everything mocked via `unittest.mock`.

**`tests/sync/test_engine.py`**
- Poll worker reads cursor, calls `fetch_logs`, inserts batch, advances cursor
- Poll worker defaults start to `now - poll_interval` when no cursor exists
- Stream worker flushes at batch size 100
- Stream worker flushes on 5 s timeout with < 100 events
- Backoff doubles on consecutive failures, resets on success
- SyncEngine starts one worker per source; stops all on shutdown

**`tests/db/test_postgres.py`**
- `insert_logs` with mock asyncpg pool — verifies SQL and parameter binding
- `get_cursor` returns `None` before upsert, correct `datetime` after
- `upsert_cursor` issues correct SQL with updated timestamp

**`tests/adapters/test_loki.py`** (extend)
- Deterministic ID: same raw dict always produces same `event.id`

**`tests/api/test_health.py`** (extend)
- Health route passes after lifespan refactor

---

## 8. Files Changed / Created

| File | Action |
|------|--------|
| `db/migrations/001_init.sql` | Create |
| `db/postgres.py` | Create |
| `sync/engine.py` | Create |
| `adapters/loki.py` | Modify — deterministic UUID5 in `normalise()` |
| `api/main.py` | Modify — add lifespan, load config, start SyncEngine |
| `requirements.txt` | Modify — add `asyncpg==0.29.0` |
| `tests/sync/__init__.py` | Create |
| `tests/sync/test_engine.py` | Create |
| `tests/db/__init__.py` | Create |
| `tests/db/test_postgres.py` | Create |

---

## 9. Out of Scope for M2

- Embedding via OpenAI (M3)
- Qdrant vector storage (M3)
- Anomaly scoring (M3)
- Full ingestion pipeline (M3)
- `audit_log` table (M4+)
- Multiple adapter types beyond LokiAdapter (future)
