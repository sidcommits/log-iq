# LogIQ M3 — Ingestion Pipeline + Semantic Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a decoupled `IngestionWorker` that polls PostgreSQL for unembedded logs, embeds them via OpenAI, and stores vectors in Qdrant; then expose `POST /api/search` that queries those vectors with optional metadata filters and falls back to PostgreSQL text search when similarity is low.

**Architecture:** `SyncEngine` writes `LogEvent`s to PostgreSQL with `embedded_at = NULL`. `IngestionWorker` polls for unembedded rows every 5s, calls OpenAI `text-embedding-3-small`, upserts into Qdrant, then marks rows embedded. `POST /api/search` embeds the query, runs Qdrant KNN with optional filters, falls back to PostgreSQL `ILIKE` if top score < 0.75 or no results, deduplicates chunked logs by `log_id`, and returns full `LogEvent` objects with similarity scores.

**Tech Stack:** `qdrant-client` (async), `openai` (AsyncOpenAI), `tiktoken` (token counting), `asyncpg` (existing), `fastapi` (existing), `httpx` (existing, for tests).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | modify | add qdrant-client, openai, tiktoken |
| `db/migrations/002_ingestion.sql` | create | `embedded_at` column + partial index |
| `db/postgres.py` | modify | update migration loader + 5 new functions |
| `db/qdrant.py` | create | client init, `ensure_collection`, `upsert_vectors`, `search_vectors` |
| `ingestion/pipeline.py` | create | `chunk_message`, `embed_texts`, `IngestionWorker` |
| `intelligence/search.py` | create | `SearchFilters`, `SearchResponse`, `_build_qdrant_filter`, `semantic_search` |
| `api/routes/search.py` | create | `POST /api/search` route |
| `api/main.py` | modify | Qdrant + `IngestionWorker` + search router in lifespan |
| `tests/db/test_qdrant.py` | create | unit tests for `db/qdrant.py` |
| `tests/db/test_postgres.py` | modify | tests for 5 new postgres functions |
| `tests/ingestion/__init__.py` | create | empty package marker |
| `tests/ingestion/test_pipeline.py` | create | unit tests for `IngestionWorker` |
| `tests/intelligence/__init__.py` | create | empty package marker |
| `tests/intelligence/test_search.py` | create | unit tests for `semantic_search` |
| `tests/api/test_search.py` | create | HTTP tests for `POST /api/search` |
| `tests/api/conftest.py` | modify | patch new lifespan deps |

---

## Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add three packages to requirements.txt**

  Open `requirements.txt` and append these three lines:
  ```
  qdrant-client==1.9.1
  openai==1.54.0
  tiktoken==0.8.0
  ```

- [ ] **Step 2: Install and verify**

  ```bash
  pip install qdrant-client==1.9.1 openai==1.54.0 tiktoken==0.8.0
  python -c "from qdrant_client import AsyncQdrantClient; from openai import AsyncOpenAI; import tiktoken; print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 3: Commit**

  ```bash
  git add requirements.txt
  git commit -m "chore: add qdrant-client, openai, tiktoken dependencies"
  ```

---

## Task 2: DB migration 002 + postgres additions

**Files:**
- Create: `db/migrations/002_ingestion.sql`
- Modify: `db/postgres.py`
- Modify: `tests/db/test_postgres.py`

### Step 2a — Write failing tests first

- [ ] **Step 1: Add failing tests to tests/db/test_postgres.py**

  Append to the bottom of `tests/db/test_postgres.py`:

  ```python
  from db.postgres import fetch_logs_by_ids, fetch_logs_by_text, fetch_unembedded_logs, mark_embedded


  @pytest.mark.asyncio
  async def test_fetch_unembedded_logs_queries_where_embedded_at_is_null():
      mock_pool, mock_conn = _make_mock_pool()
      mock_conn.fetch.return_value = []

      result = await fetch_unembedded_logs(mock_pool, limit=50)

      mock_conn.fetch.assert_called_once()
      sql, limit_arg = mock_conn.fetch.call_args[0]
      assert "embedded_at IS NULL" in sql
      assert limit_arg == 50
      assert result == []


  @pytest.mark.asyncio
  async def test_mark_embedded_executes_update():
      mock_pool, mock_conn = _make_mock_pool()

      await mark_embedded(mock_pool, ["id-1", "id-2"])

      mock_conn.execute.assert_called_once()
      sql, ids_arg = mock_conn.execute.call_args[0]
      assert "UPDATE logs SET embedded_at" in sql
      assert ids_arg == ["id-1", "id-2"]


  @pytest.mark.asyncio
  async def test_mark_embedded_skips_empty_list():
      mock_pool, mock_conn = _make_mock_pool()

      await mark_embedded(mock_pool, [])

      mock_conn.execute.assert_not_called()


  @pytest.mark.asyncio
  async def test_fetch_logs_by_ids_returns_empty_without_query():
      mock_pool, mock_conn = _make_mock_pool()

      result = await fetch_logs_by_ids(mock_pool, [])

      mock_conn.fetch.assert_not_called()
      assert result == []


  @pytest.mark.asyncio
  async def test_fetch_logs_by_text_queries_ilike():
      mock_pool, mock_conn = _make_mock_pool()
      mock_conn.fetch.return_value = []

      result = await fetch_logs_by_text(mock_pool, "auth error", limit=10)

      mock_conn.fetch.assert_called_once()
      sql, query_arg, limit_arg = mock_conn.fetch.call_args[0]
      assert "ILIKE" in sql
      assert "%auth error%" in query_arg
      assert limit_arg == 10
      assert result == []
  ```

- [ ] **Step 2: Run tests — expect FAIL (ImportError)**

  ```bash
  pytest tests/db/test_postgres.py -k "unembedded or mark_embedded or by_ids or by_text" -v
  ```
  Expected: `ImportError: cannot import name 'fetch_unembedded_logs'`

### Step 2b — Create migration

- [ ] **Step 3: Create db/migrations/002_ingestion.sql**

  ```sql
  ALTER TABLE logs ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ NULL;

  CREATE INDEX IF NOT EXISTS idx_logs_unembedded ON logs (id)
  WHERE embedded_at IS NULL;
  ```

### Step 2c — Implement postgres additions

- [ ] **Step 4: Update db/postgres.py**

  Replace the entire file with:

  ```python
  from __future__ import annotations

  from pathlib import Path

  import asyncpg

  from models.log_event import LogEvent, SeverityLevel

  _MIGRATIONS_DIR = Path(__file__).parent / "migrations"
  _MIGRATION_SQL = "\n".join(
      p.read_text()
      for p in sorted(_MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
  )


  def _row_to_log_event(row) -> LogEvent:
      return LogEvent(
          id=row["id"],
          timestamp=row["timestamp"],
          severity=SeverityLevel(row["severity"]),
          service=row["service"],
          environment=row["environment"],
          trace_id=row["trace_id"],
          span_id=row["span_id"],
          message=row["message"],
          metadata=row["metadata"] or {},
          raw=row["raw"] or {},
          source=row["source"],
      )


  async def init_pool(dsn: str) -> asyncpg.Pool:
      pool = await asyncpg.create_pool(dsn)
      async with pool.acquire() as conn:
          await conn.execute(_MIGRATION_SQL)
      return pool


  async def get_cursor(pool: asyncpg.Pool, source_name: str) -> datetime | None:
      async with pool.acquire() as conn:
          row = await conn.fetchrow(
              "SELECT last_synced_at FROM sync_cursors WHERE source_name = $1",
              source_name,
          )
      return row["last_synced_at"] if row else None


  async def upsert_cursor(pool: asyncpg.Pool, source_name: str, ts) -> None:
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


  async def fetch_unembedded_logs(pool: asyncpg.Pool, limit: int = 100) -> list[LogEvent]:
      async with pool.acquire() as conn:
          rows = await conn.fetch(
              "SELECT * FROM logs WHERE embedded_at IS NULL ORDER BY timestamp ASC LIMIT $1",
              limit,
          )
      return [_row_to_log_event(row) for row in rows]


  async def mark_embedded(pool: asyncpg.Pool, ids: list[str]) -> None:
      if not ids:
          return
      async with pool.acquire() as conn:
          await conn.execute(
              "UPDATE logs SET embedded_at = NOW() WHERE id = ANY($1)",
              ids,
          )


  async def fetch_logs_by_ids(pool: asyncpg.Pool, ids: list[str]) -> list[LogEvent]:
      if not ids:
          return []
      async with pool.acquire() as conn:
          rows = await conn.fetch(
              "SELECT * FROM logs WHERE id = ANY($1)",
              ids,
          )
      return [_row_to_log_event(row) for row in rows]


  async def fetch_logs_by_text(pool: asyncpg.Pool, query: str, limit: int) -> list[LogEvent]:
      async with pool.acquire() as conn:
          rows = await conn.fetch(
              "SELECT * FROM logs WHERE message ILIKE $1 ORDER BY timestamp DESC LIMIT $2",
              f"%{query}%",
              limit,
          )
      return [_row_to_log_event(row) for row in rows]
  ```

  Note: `get_cursor` lost its `datetime` import — add it back at the top:
  ```python
  from datetime import datetime
  ```
  Full import block:
  ```python
  from __future__ import annotations

  from datetime import datetime
  from pathlib import Path

  import asyncpg

  from models.log_event import LogEvent, SeverityLevel
  ```

- [ ] **Step 5: Run tests — expect PASS**

  ```bash
  pytest tests/db/test_postgres.py -v
  ```
  Expected: all tests pass, including the 5 new ones.

- [ ] **Step 6: Commit**

  ```bash
  git add db/migrations/002_ingestion.sql db/postgres.py tests/db/test_postgres.py
  git commit -m "feat: migration 002 embedded_at column + postgres fetch/mark/text helpers (TDD)"
  ```

---

## Task 3: db/qdrant.py — Qdrant client + helpers

**Files:**
- Create: `db/qdrant.py`
- Create: `tests/db/test_qdrant.py`

- [ ] **Step 1: Write failing tests — create tests/db/test_qdrant.py**

  ```python
  from unittest.mock import AsyncMock, MagicMock

  import pytest
  from qdrant_client.models import PointStruct

  from db.qdrant import ensure_collection, search_vectors, upsert_vectors


  @pytest.mark.asyncio
  async def test_ensure_collection_creates_when_absent():
      client = AsyncMock()
      mock_response = MagicMock()
      mock_response.collections = []
      client.get_collections.return_value = mock_response

      await ensure_collection(client, "test_col")

      client.create_collection.assert_called_once()
      kwargs = client.create_collection.call_args.kwargs
      assert kwargs["collection_name"] == "test_col"


  @pytest.mark.asyncio
  async def test_ensure_collection_skips_when_present():
      client = AsyncMock()
      existing = MagicMock()
      existing.name = "log_events"
      mock_response = MagicMock()
      mock_response.collections = [existing]
      client.get_collections.return_value = mock_response

      await ensure_collection(client, "log_events")

      client.create_collection.assert_not_called()


  @pytest.mark.asyncio
  async def test_upsert_vectors_calls_client_upsert():
      client = AsyncMock()
      points = [
          PointStruct(id="abc-123", vector=[0.1] * 1536, payload={"log_id": "abc-123"})
      ]

      await upsert_vectors(client, points, "log_events")

      client.upsert.assert_called_once_with(collection_name="log_events", points=points)


  @pytest.mark.asyncio
  async def test_upsert_vectors_skips_empty_list():
      client = AsyncMock()

      await upsert_vectors(client, [], "log_events")

      client.upsert.assert_not_called()


  @pytest.mark.asyncio
  async def test_search_vectors_returns_log_ids_and_scores():
      client = AsyncMock()
      hit = MagicMock()
      hit.payload = {"log_id": "log-abc"}
      hit.score = 0.91
      client.search.return_value = [hit]

      results = await search_vectors(client, [0.1] * 1536, None, limit=5)

      assert results == [("log-abc", 0.91)]
      call_kwargs = client.search.call_args.kwargs
      assert call_kwargs["collection_name"] == "log_events"
      assert call_kwargs["limit"] == 5
      assert call_kwargs["with_payload"] is True


  @pytest.mark.asyncio
  async def test_search_vectors_returns_empty_when_no_hits():
      client = AsyncMock()
      client.search.return_value = []

      results = await search_vectors(client, [0.1] * 1536, None, limit=5)

      assert results == []
  ```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

  ```bash
  pytest tests/db/test_qdrant.py -v
  ```
  Expected: `ImportError: cannot import name 'ensure_collection' from 'db.qdrant'`

- [ ] **Step 3: Create db/qdrant.py**

  ```python
  from __future__ import annotations

  from qdrant_client import AsyncQdrantClient
  from qdrant_client.models import Distance, Filter, PointStruct, VectorParams

  _COLLECTION = "log_events"
  _VECTOR_SIZE = 1536


  async def init_qdrant(host: str, port: int) -> AsyncQdrantClient:
      return AsyncQdrantClient(host=host, port=port)


  async def ensure_collection(
      client: AsyncQdrantClient,
      collection: str = _COLLECTION,
  ) -> None:
      existing = await client.get_collections()
      names = {c.name for c in existing.collections}
      if collection not in names:
          await client.create_collection(
              collection_name=collection,
              vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
          )


  async def upsert_vectors(
      client: AsyncQdrantClient,
      points: list[PointStruct],
      collection: str = _COLLECTION,
  ) -> None:
      if not points:
          return
      await client.upsert(collection_name=collection, points=points)


  async def search_vectors(
      client: AsyncQdrantClient,
      query_vector: list[float],
      qdrant_filter: Filter | None = None,
      limit: int = 20,
      score_threshold: float = 0.0,
      collection: str = _COLLECTION,
  ) -> list[tuple[str, float]]:
      """Returns [(log_id, score)] extracted from point payload, sorted by score desc."""
      hits = await client.search(
          collection_name=collection,
          query_vector=query_vector,
          limit=limit,
          query_filter=qdrant_filter,
          score_threshold=score_threshold,
          with_payload=True,
      )
      return [(hit.payload["log_id"], hit.score) for hit in hits]
  ```

- [ ] **Step 4: Run tests — expect PASS**

  ```bash
  pytest tests/db/test_qdrant.py -v
  ```
  Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

  ```bash
  git add db/qdrant.py tests/db/test_qdrant.py
  git commit -m "feat: db/qdrant.py — init_qdrant, ensure_collection, upsert_vectors, search_vectors (TDD)"
  ```

---

## Task 4: ingestion/pipeline.py — IngestionWorker

**Files:**
- Create: `ingestion/pipeline.py`
- Create: `tests/ingestion/__init__.py`
- Create: `tests/ingestion/test_pipeline.py`

- [ ] **Step 1: Create tests/ingestion/__init__.py (empty)**

  ```bash
  touch tests/ingestion/__init__.py
  ```

- [ ] **Step 2: Write failing tests — create tests/ingestion/test_pipeline.py**

  ```python
  from datetime import datetime, timezone
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest

  from models.log_event import LogEvent, SeverityLevel


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


  def test_chunk_message_returns_single_chunk_for_short_text():
      from ingestion.pipeline import chunk_message
      result = chunk_message("short message")
      assert result == ["short message"]


  def test_chunk_message_splits_text_exceeding_512_tokens():
      from ingestion.pipeline import chunk_message
      # 600 repetitions of "word " is well above 512 tokens
      long_text = " ".join(["word"] * 600)
      result = chunk_message(long_text)
      assert len(result) > 1


  @pytest.mark.asyncio
  async def test_process_batch_embeds_and_upserts_then_marks():
      from ingestion.pipeline import IngestionWorker

      pool = MagicMock()
      openai_client = AsyncMock()
      qdrant_client = AsyncMock()
      event = _make_event()

      with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]) as mock_fetch, \
           patch("ingestion.pipeline.mark_embedded") as mock_mark, \
           patch("ingestion.pipeline.upsert_vectors") as mock_upsert, \
           patch("ingestion.pipeline.embed_texts", return_value=[[0.1] * 1536]):

          worker = IngestionWorker(pool, openai_client, qdrant_client)
          result = await worker._process_batch()

      assert result is True
      mock_fetch.assert_called_once_with(pool, 100)
      mock_upsert.assert_called_once()
      ids_arg = mock_mark.call_args[0][1]
      assert "test-id-001" in ids_arg


  @pytest.mark.asyncio
  async def test_process_batch_returns_false_when_no_events():
      from ingestion.pipeline import IngestionWorker

      pool = MagicMock()
      event = _make_event()

      with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[]):
          worker = IngestionWorker(pool, AsyncMock(), AsyncMock())
          result = await worker._process_batch()

      assert result is False


  @pytest.mark.asyncio
  async def test_process_batch_does_not_mark_embedded_on_openai_failure():
      from ingestion.pipeline import IngestionWorker

      event = _make_event()

      with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]), \
           patch("ingestion.pipeline.embed_texts", side_effect=Exception("OpenAI down")), \
           patch("ingestion.pipeline.mark_embedded") as mock_mark:

          worker = IngestionWorker(MagicMock(), AsyncMock(), AsyncMock())
          with pytest.raises(Exception, match="OpenAI down"):
              await worker._process_batch()

      mock_mark.assert_not_called()


  @pytest.mark.asyncio
  async def test_worker_start_stop_lifecycle():
      from ingestion.pipeline import IngestionWorker
      import asyncio

      with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[]):
          worker = IngestionWorker(MagicMock(), AsyncMock(), AsyncMock(), poll_interval=0.01)
          await worker.start()
          assert worker._task is not None
          await asyncio.sleep(0.05)
          await worker.stop()
          assert worker._task.done()
  ```

- [ ] **Step 3: Run — expect FAIL (ImportError)**

  ```bash
  pytest tests/ingestion/test_pipeline.py -v
  ```
  Expected: `ImportError: cannot import name 'chunk_message' from 'ingestion.pipeline'`

- [ ] **Step 4: Create ingestion/pipeline.py**

  ```python
  from __future__ import annotations

  import asyncio
  import logging
  import uuid
  from typing import Any

  import tiktoken
  from openai import AsyncOpenAI
  from qdrant_client import AsyncQdrantClient
  from qdrant_client.models import PointStruct

  from db.postgres import fetch_unembedded_logs, mark_embedded
  from db.qdrant import upsert_vectors
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
      ) -> None:
          self._pool = pool
          self._openai = openai_client
          self._qdrant = qdrant_client
          self._poll_interval = poll_interval
          self._batch_size = batch_size
          self._collection = collection
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

          # Build (event, chunk_index, chunk_text) tuples for all events
          items: list[tuple[LogEvent, int, str]] = [
              (event, i, chunk)
              for event in events
              for i, chunk in enumerate(chunk_message(event.message))
          ]

          # Embed all chunks in one API call
          embeddings = await embed_texts(self._openai, [text for _, _, text in items])

          # Count chunks per event to decide point ID strategy
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
          await mark_embedded(self._pool, [e.id for e in events])
          return True
  ```

- [ ] **Step 5: Run tests — expect PASS**

  ```bash
  pytest tests/ingestion/test_pipeline.py -v
  ```
  Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add ingestion/pipeline.py tests/ingestion/__init__.py tests/ingestion/test_pipeline.py
  git commit -m "feat: IngestionWorker — poll, chunk, embed, upsert, mark (TDD)"
  ```

---

## Task 5: intelligence/search.py — semantic_search

**Files:**
- Create: `intelligence/search.py`
- Create: `tests/intelligence/__init__.py`
- Create: `tests/intelligence/test_search.py`

- [ ] **Step 1: Create tests/intelligence/__init__.py (empty)**

  ```bash
  touch tests/intelligence/__init__.py
  ```

- [ ] **Step 2: Write failing tests — create tests/intelligence/test_search.py**

  ```python
  from datetime import datetime, timezone
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest

  from models.log_event import LogEvent, SeverityLevel


  def _make_event(**kwargs) -> LogEvent:
      defaults = dict(
          id="log-001",
          timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
          severity=SeverityLevel.ERROR,
          service="auth-service",
          environment="production",
          message="auth failure",
          source="loki",
      )
      return LogEvent(**{**defaults, **kwargs})


  def test_build_qdrant_filter_returns_none_for_empty_filters():
      from intelligence.search import SearchFilters, _build_qdrant_filter
      result = _build_qdrant_filter(SearchFilters())
      assert result is None


  def test_build_qdrant_filter_single_severity():
      from intelligence.search import SearchFilters, _build_qdrant_filter
      result = _build_qdrant_filter(SearchFilters(severity="ERROR"))
      assert result is not None
      assert len(result.must) == 1
      assert result.must[0].key == "severity"


  def test_build_qdrant_filter_time_range():
      from intelligence.search import SearchFilters, _build_qdrant_filter
      result = _build_qdrant_filter(SearchFilters(
          start_time=datetime(2026, 5, 6, 0, 0, tzinfo=timezone.utc),
          end_time=datetime(2026, 5, 6, 23, 59, tzinfo=timezone.utc),
      ))
      assert result is not None
      cond = result.must[0]
      assert cond.key == "timestamp_unix"
      assert cond.range.gte is not None
      assert cond.range.lte is not None


  def test_build_qdrant_filter_multiple_conditions():
      from intelligence.search import SearchFilters, _build_qdrant_filter
      result = _build_qdrant_filter(SearchFilters(severity="ERROR", service="auth-service"))
      assert len(result.must) == 2


  @pytest.mark.asyncio
  async def test_semantic_search_returns_qdrant_results_above_threshold():
      from intelligence.search import semantic_search, SearchFilters
      event = _make_event()

      with patch("intelligence.search.embed_texts", return_value=[[0.1] * 1536]), \
           patch("intelligence.search.search_vectors", return_value=[("log-001", 0.90)]), \
           patch("intelligence.search.fetch_logs_by_ids", return_value=[event]):

          result = await semantic_search(
              query="auth failure",
              filters=None,
              limit=10,
              pool=MagicMock(),
              openai_client=AsyncMock(),
              qdrant_client=AsyncMock(),
          )

      assert result.fallback_used is False
      assert len(result.results) == 1
      assert result.results[0].score == 0.90
      assert result.results[0].log.id == "log-001"


  @pytest.mark.asyncio
  async def test_semantic_search_uses_pg_fallback_when_score_below_threshold():
      from intelligence.search import semantic_search
      event = _make_event()

      with patch("intelligence.search.embed_texts", return_value=[[0.1] * 1536]), \
           patch("intelligence.search.search_vectors", return_value=[("log-001", 0.50)]), \
           patch("intelligence.search.fetch_logs_by_text", return_value=[event]):

          result = await semantic_search(
              query="auth failure",
              filters=None,
              limit=10,
              pool=MagicMock(),
              openai_client=AsyncMock(),
              qdrant_client=AsyncMock(),
          )

      assert result.fallback_used is True
      assert result.results[0].score == 0.0


  @pytest.mark.asyncio
  async def test_semantic_search_uses_pg_fallback_when_no_qdrant_results():
      from intelligence.search import semantic_search
      event = _make_event()

      with patch("intelligence.search.embed_texts", return_value=[[0.1] * 1536]), \
           patch("intelligence.search.search_vectors", return_value=[]), \
           patch("intelligence.search.fetch_logs_by_text", return_value=[event]):

          result = await semantic_search(
              query="auth failure",
              filters=None,
              limit=10,
              pool=MagicMock(),
              openai_client=AsyncMock(),
              qdrant_client=AsyncMock(),
          )

      assert result.fallback_used is True


  @pytest.mark.asyncio
  async def test_semantic_search_deduplicates_chunked_log():
      from intelligence.search import semantic_search
      event = _make_event()

      # Same log_id returned twice (two chunks), different scores
      with patch("intelligence.search.embed_texts", return_value=[[0.1] * 1536]), \
           patch("intelligence.search.search_vectors", return_value=[("log-001", 0.92), ("log-001", 0.88)]), \
           patch("intelligence.search.fetch_logs_by_ids", return_value=[event]):

          result = await semantic_search(
              query="auth failure",
              filters=None,
              limit=10,
              pool=MagicMock(),
              openai_client=AsyncMock(),
              qdrant_client=AsyncMock(),
          )

      # One log, highest score wins
      assert len(result.results) == 1
      assert result.results[0].score == 0.92
  ```

- [ ] **Step 3: Run — expect FAIL (ImportError)**

  ```bash
  pytest tests/intelligence/test_search.py -v
  ```
  Expected: `ImportError: cannot import name 'semantic_search' from 'intelligence.search'`

- [ ] **Step 4: Create intelligence/search.py**

  ```python
  from __future__ import annotations

  import asyncio
  from datetime import datetime
  from typing import Any

  from openai import AsyncOpenAI
  from pydantic import BaseModel
  from qdrant_client import AsyncQdrantClient
  from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

  from db.postgres import fetch_logs_by_ids, fetch_logs_by_text
  from db.qdrant import search_vectors
  from ingestion.pipeline import embed_texts
  from models.log_event import LogEvent

  _FALLBACK_THRESHOLD = 0.75


  class SearchFilters(BaseModel):
      severity: str | None = None
      service: str | None = None
      environment: str | None = None
      start_time: datetime | None = None
      end_time: datetime | None = None


  class SearchResult(BaseModel):
      log: LogEvent
      score: float


  class SearchResponse(BaseModel):
      results: list[SearchResult]
      total: int
      fallback_used: bool


  def _build_qdrant_filter(filters: SearchFilters) -> Filter | None:
      conditions = []
      if filters.severity:
          conditions.append(FieldCondition(key="severity", match=MatchValue(value=filters.severity)))
      if filters.service:
          conditions.append(FieldCondition(key="service", match=MatchValue(value=filters.service)))
      if filters.environment:
          conditions.append(
              FieldCondition(key="environment", match=MatchValue(value=filters.environment))
          )
      if filters.start_time or filters.end_time:
          range_kwargs: dict[str, float] = {}
          if filters.start_time:
              range_kwargs["gte"] = filters.start_time.timestamp()
          if filters.end_time:
              range_kwargs["lte"] = filters.end_time.timestamp()
          conditions.append(FieldCondition(key="timestamp_unix", range=Range(**range_kwargs)))
      return Filter(must=conditions) if conditions else None


  async def semantic_search(
      query: str,
      filters: SearchFilters | None,
      limit: int,
      pool: Any,
      openai_client: AsyncOpenAI,
      qdrant_client: AsyncQdrantClient,
      collection: str = "log_events",
  ) -> SearchResponse:
      [query_vector] = await embed_texts(openai_client, [query])

      qdrant_filter = _build_qdrant_filter(filters) if filters else None
      hits = await search_vectors(
          qdrant_client, query_vector, qdrant_filter, limit=limit, collection=collection
      )

      if not hits or hits[0][1] < _FALLBACK_THRESHOLD:
          events = await fetch_logs_by_text(pool, query, limit)
          results = [SearchResult(log=e, score=0.0) for e in events]
          return SearchResponse(results=results, total=len(results), fallback_used=True)

      # Dedup by log_id — multiple chunks may match; keep highest score
      seen: dict[str, float] = {}
      for log_id, score in hits:
          if log_id not in seen or score > seen[log_id]:
              seen[log_id] = score

      events = await fetch_logs_by_ids(pool, list(seen.keys()))
      events_map = {e.id: e for e in events}

      results = sorted(
          [
              SearchResult(log=events_map[log_id], score=score)
              for log_id, score in seen.items()
              if log_id in events_map
          ],
          key=lambda r: r.score,
          reverse=True,
      )

      return SearchResponse(results=results[:limit], total=len(results), fallback_used=False)
  ```

- [ ] **Step 5: Run tests — expect PASS**

  ```bash
  pytest tests/intelligence/test_search.py -v
  ```
  Expected: all 7 tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add intelligence/search.py tests/intelligence/__init__.py tests/intelligence/test_search.py
  git commit -m "feat: intelligence/search.py — semantic_search with Qdrant KNN + PG fallback (TDD)"
  ```

---

## Task 6: api/routes/search.py + api/main.py wiring

**Files:**
- Create: `api/routes/search.py`
- Create: `tests/api/test_search.py`
- Modify: `api/main.py`
- Modify: `tests/api/conftest.py`

- [ ] **Step 1: Write failing tests — create tests/api/test_search.py**

  ```python
  from datetime import datetime, timezone
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest
  from fastapi import FastAPI
  from httpx import ASGITransport, AsyncClient

  from intelligence.search import SearchResponse, SearchResult
  from models.log_event import LogEvent, SeverityLevel


  def _make_event(**kwargs) -> LogEvent:
      defaults = dict(
          id="log-001",
          timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
          severity=SeverityLevel.ERROR,
          service="auth-service",
          environment="production",
          message="auth failure",
          source="loki",
      )
      return LogEvent(**{**defaults, **kwargs})


  @pytest.fixture
  def test_app():
      from api.routes.search import router as search_router
      app = FastAPI()
      app.include_router(search_router, prefix="/api")
      app.state.db_pool = MagicMock()
      app.state.openai_client = MagicMock()
      app.state.qdrant_client = MagicMock()
      return app


  @pytest.mark.asyncio
  async def test_search_returns_200_with_results(test_app):
      event = _make_event()
      mock_response = SearchResponse(
          results=[SearchResult(log=event, score=0.90)],
          total=1,
          fallback_used=False,
      )

      with patch("api.routes.search.semantic_search", return_value=mock_response):
          async with AsyncClient(
              transport=ASGITransport(app=test_app), base_url="http://test"
          ) as ac:
              resp = await ac.post("/api/search", json={"query": "auth failure"})

      assert resp.status_code == 200
      body = resp.json()
      assert body["total"] == 1
      assert body["fallback_used"] is False
      assert body["results"][0]["score"] == 0.90


  @pytest.mark.asyncio
  async def test_search_returns_422_for_whitespace_only_query(test_app):
      async with AsyncClient(
          transport=ASGITransport(app=test_app), base_url="http://test"
      ) as ac:
          resp = await ac.post("/api/search", json={"query": "   "})

      assert resp.status_code == 422


  @pytest.mark.asyncio
  async def test_search_returns_503_on_search_exception(test_app):
      with patch(
          "api.routes.search.semantic_search", side_effect=Exception("OpenAI down")
      ):
          async with AsyncClient(
              transport=ASGITransport(app=test_app), base_url="http://test"
          ) as ac:
              resp = await ac.post("/api/search", json={"query": "auth failure"})

      assert resp.status_code == 503


  @pytest.mark.asyncio
  async def test_search_includes_fallback_flag_in_response(test_app):
      event = _make_event()
      mock_response = SearchResponse(
          results=[SearchResult(log=event, score=0.0)],
          total=1,
          fallback_used=True,
      )

      with patch("api.routes.search.semantic_search", return_value=mock_response):
          async with AsyncClient(
              transport=ASGITransport(app=test_app), base_url="http://test"
          ) as ac:
              resp = await ac.post("/api/search", json={"query": "auth failure"})

      assert resp.json()["fallback_used"] is True
  ```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

  ```bash
  pytest tests/api/test_search.py -v
  ```
  Expected: `ImportError: cannot import name 'router' from 'api.routes.search'`

- [ ] **Step 3: Create api/routes/search.py**

  ```python
  from __future__ import annotations

  import asyncio

  from fastapi import APIRouter, HTTPException, Request
  from pydantic import BaseModel

  from intelligence.search import SearchFilters, SearchResponse, semantic_search

  router = APIRouter()


  class SearchRequest(BaseModel):
      query: str
      filters: SearchFilters | None = None
      limit: int = 20


  @router.post("/search", response_model=SearchResponse)
  async def search_logs(body: SearchRequest, request: Request) -> SearchResponse:
      if not body.query.strip():
          raise HTTPException(status_code=422, detail="query must not be empty")
      try:
          return await asyncio.wait_for(
              semantic_search(
                  query=body.query,
                  filters=body.filters,
                  limit=min(body.limit, 100),
                  pool=request.app.state.db_pool,
                  openai_client=request.app.state.openai_client,
                  qdrant_client=request.app.state.qdrant_client,
              ),
              timeout=30.0,
          )
      except asyncio.TimeoutError:
          raise HTTPException(status_code=503, detail="search timed out")
      except HTTPException:
          raise
      except Exception as exc:
          raise HTTPException(status_code=503, detail=str(exc))
  ```

- [ ] **Step 4: Run route tests — expect PASS**

  ```bash
  pytest tests/api/test_search.py -v
  ```
  Expected: all 4 tests pass.

- [ ] **Step 5: Update api/main.py to wire Qdrant + IngestionWorker + search router**

  Replace the entire file with:

  ```python
  import uuid
  from contextlib import asynccontextmanager
  from pathlib import Path

  import yaml
  from fastapi import FastAPI, Request
  from fastapi.middleware.cors import CORSMiddleware
  from fastapi.responses import Response
  from openai import AsyncOpenAI
  from prometheus_fastapi_instrumentator import Instrumentator

  from api.routes.health import router as health_router
  from api.routes.search import router as search_router
  from db.postgres import init_pool
  from db.qdrant import ensure_collection, init_qdrant
  from ingestion.pipeline import IngestionWorker
  from sync.engine import SyncEngine

  _config: dict = yaml.safe_load(
      (Path(__file__).parent.parent / "config.yaml").read_text()
  )


  @asynccontextmanager
  async def lifespan(app: FastAPI):
      app.state.db_pool = await init_pool(dsn=_config["database"]["url"])

      qdrant_cfg = _config["qdrant"]
      app.state.qdrant_client = await init_qdrant(
          host=qdrant_cfg["host"], port=qdrant_cfg["port"]
      )
      await ensure_collection(app.state.qdrant_client, qdrant_cfg.get("collection", "log_events"))

      app.state.openai_client = AsyncOpenAI()  # reads OPENAI_API_KEY from env

      engine = SyncEngine(config=_config, pool=app.state.db_pool)
      await engine.start()

      ingestion_worker = IngestionWorker(
          pool=app.state.db_pool,
          openai_client=app.state.openai_client,
          qdrant_client=app.state.qdrant_client,
          batch_size=_config["ingestion"].get("batch_size", 100),
          collection=qdrant_cfg.get("collection", "log_events"),
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
  ```

- [ ] **Step 6: Update tests/api/conftest.py to patch new lifespan deps**

  Replace the entire file with:

  ```python
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

- [ ] **Step 7: Run the full test suite — expect all tests pass**

  ```bash
  pytest -v
  ```
  Expected: all tests pass including the full `tests/api/` suite.

- [ ] **Step 8: Commit**

  ```bash
  git add api/routes/search.py api/main.py tests/api/test_search.py tests/api/conftest.py
  git commit -m "feat: POST /api/search route + wire IngestionWorker and Qdrant into lifespan (TDD)"
  ```

---

## Final verification

- [ ] **Run complete test suite one last time**

  ```bash
  pytest -v --tb=short
  ```
  Expected: all tests green, no warnings about missing fixtures.
