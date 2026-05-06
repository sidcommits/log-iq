# LogIQ M3 — Ingestion Pipeline + Semantic Search Design

## 1. Objective

Build two tightly coupled capabilities on top of the M2 sync engine:

1. **Ingestion Pipeline** — a decoupled background worker that picks up `LogEvent`s written to PostgreSQL by the sync engine, embeds them via OpenAI, and stores vectors in Qdrant.
2. **Semantic Search** — a `POST /api/search` endpoint that embeds a natural-language query, runs KNN over Qdrant with optional metadata filters, and falls back to PostgreSQL text search when similarity is too low.

M2 deliberately deferred embedding and Qdrant. M3 closes that gap. Anomaly scoring is out of scope (M5).

---

## 2. Architecture

### 2.1 Data Flow

```
SyncEngine → PostgreSQL logs (embedded_at = NULL)
                    ↓
         IngestionWorker polls every 5s
         SELECT ... WHERE embedded_at IS NULL LIMIT 100
                    ↓
         chunk messages >512 tokens
                    ↓
         OpenAI embed (text-embedding-3-small, 1536d)
                    ↓
         Qdrant upsert (vector + payload metadata)
                    ↓
         PostgreSQL UPDATE embedded_at = NOW()

POST /api/search
         ↓
    embed query via OpenAI (text-embedding-3-small)
         ↓
    Qdrant KNN search (optional metadata filters)
         ↓
    top score < 0.75 OR 0 results → PostgreSQL ILIKE fallback
         ↓
    fetch full LogEvents by ID from PostgreSQL
         ↓
    return [{ log: LogEvent, score: float }], fallback_used: bool
```

### 2.2 Components

| File | Role |
|---|---|
| `db/migrations/002_ingestion.sql` | `embedded_at` column + partial index on `logs` |
| `db/qdrant.py` | Qdrant client, `ensure_collection()`, `upsert_vectors()`, `search_vectors()` |
| `db/postgres.py` *(+3 fns)* | `fetch_unembedded_logs()`, `mark_embedded()`, `fetch_logs_by_ids()` |
| `ingestion/pipeline.py` | `IngestionWorker` — poll → chunk → embed → upsert → mark |
| `intelligence/search.py` | `semantic_search()` — embed, KNN, fallback, assemble |
| `api/routes/search.py` | `POST /api/search` route |
| `api/main.py` *(modified)* | init Qdrant + start `IngestionWorker` in lifespan, register router |

---

## 3. Database Schema (`db/migrations/002_ingestion.sql`)

```sql
ALTER TABLE logs ADD COLUMN embedded_at TIMESTAMPTZ NULL;

CREATE INDEX idx_logs_unembedded ON logs (id)
WHERE embedded_at IS NULL;
```

`embedded_at IS NULL` means "not yet embedded". The partial index keeps this query fast as the table grows.

---

## 4. `db/qdrant.py` Interface

```python
async def init_qdrant(host: str, port: int) -> AsyncQdrantClient

async def ensure_collection(client: AsyncQdrantClient, collection: str = "log_events") -> None
# Idempotent. Creates collection if absent: 1536 dims, cosine distance.

async def upsert_vectors(
    client: AsyncQdrantClient,
    points: list[PointStruct],  # id=log UUID, vector=embedding, payload=metadata
) -> None

async def search_vectors(
    client: AsyncQdrantClient,
    query_vector: list[float],
    filters: dict | None,        # maps to Qdrant Filter objects
    limit: int = 20,
    score_threshold: float = 0.0,
) -> list[tuple[str, float]]     # [(log_id, score), ...]
```

**Qdrant point payload** (6 filterable fields):
```json
{
  "log_id": "uuid",
  "timestamp": "ISO8601",
  "severity": "ERROR",
  "service": "auth-service",
  "environment": "production",
  "trace_id": "uuid-or-null"
}
```

---

## 5. `db/postgres.py` Additions

```python
async def fetch_unembedded_logs(pool, limit: int = 100) -> list[LogEvent]
# SELECT * FROM logs WHERE embedded_at IS NULL ORDER BY timestamp ASC LIMIT $1

async def mark_embedded(pool, ids: list[str]) -> None
# UPDATE logs SET embedded_at = NOW() WHERE id = ANY($1)

async def fetch_logs_by_ids(pool, ids: list[str]) -> list[LogEvent]
# SELECT * FROM logs WHERE id = ANY($1)
```

---

## 6. `ingestion/pipeline.py` — `IngestionWorker`

### Lifecycle

Same pattern as `SyncEngine`:

```python
class IngestionWorker:
    async def start(self) -> None   # launches asyncio task
    async def stop(self) -> None    # cancels task, awaits cleanup
```

### Loop

```
while running:
    batch = fetch_unembedded_logs(limit=100)
    if not batch:
        sleep(poll_interval=5s)
        continue

    chunked = chunk_long_messages(batch)  # split messages >512 tokens
    embeddings = await openai_embed(chunked)
    await qdrant_upsert(embeddings)
    await mark_embedded(ids)
    # no sleep — immediately poll for next batch while work exists
```

### Error Handling

- **OpenAI failure** (429, 503, timeout): exponential backoff — 1s, 2s, 4s … cap 30s. Log warning. Do NOT call `mark_embedded` — the batch stays `embedded_at IS NULL` and retries next cycle.
- **Qdrant upsert failure**: same backoff. Do NOT mark embedded.
- **Chunking**: messages exceeding 512 tokens (measured via tiktoken) are split. Each chunk gets its own Qdrant point with `chunk_index` in payload. All chunks share the same `log_id`. Search results dedup by `log_id` — a log matched via multiple chunks appears once (highest score wins).

### Configuration (from `config.yaml`)

```yaml
ingestion:
  poll_interval_seconds: 5
  batch_size: 100
  openai_model: text-embedding-3-small
```

---

## 7. `intelligence/search.py`

```python
async def semantic_search(
    query: str,
    filters: SearchFilters | None,
    limit: int,
    pool,
    qdrant_client,
) -> SearchResponse
```

**Filter translation** (Qdrant payload filters):
- `severity` → `MatchValue`
- `service` → `MatchValue`
- `environment` → `MatchValue`
- `start_time` / `end_time` → `Range` on `timestamp`

**Fallback condition**: top result score < 0.75 OR Qdrant returns 0 results.

**Fallback query**:
```sql
SELECT * FROM logs
WHERE message ILIKE '%{query}%'
ORDER BY timestamp DESC
LIMIT {limit}
```
Fallback results get `score = 0.0`.

---

## 8. `api/routes/search.py` — `POST /api/search`

### Request

```json
{
  "query": "auth service 500 errors last night",
  "filters": {
    "severity": "ERROR",
    "service": "auth-service",
    "environment": "production",
    "start_time": "2026-05-05T22:00:00Z",
    "end_time": "2026-05-06T06:00:00Z"
  },
  "limit": 20
}
```

### Response

```json
{
  "results": [
    {
      "log": { ...full LogEvent... },
      "score": 0.87
    }
  ],
  "total": 1,
  "fallback_used": false
}
```

### Error Cases

| Condition | Response |
|---|---|
| OpenAI embed fails | 503, standard error shape |
| Qdrant down | attempt PG fallback, `fallback_used: true` |
| `query` empty | 422 validation error |
| timeout (>30s) | 503, standard error shape |

---

## 9. `api/main.py` Changes

Three additions to the lifespan context manager (alongside existing DB pool + SyncEngine):

1. `qdrant_client = await init_qdrant(...)` + `await ensure_collection(qdrant_client)`
2. `ingestion_worker = IngestionWorker(pool, qdrant_client)` + `await ingestion_worker.start()`
3. `app.include_router(search_router, prefix="/api")`

Teardown: `await ingestion_worker.stop()` before closing DB pool.

---

## 10. Testing Strategy

| Layer | Approach |
|---|---|
| `IngestionWorker` | Mock OpenAI + mock Qdrant client. Test: fetch→embed→upsert→mark cycle. Test: OpenAI failure leaves `embedded_at` NULL. Test: empty batch triggers sleep. |
| `semantic_search()` | Mock Qdrant `search_vectors`. Test: filter construction per param. Test: fallback triggered when score < 0.75. Test: fallback triggered when 0 results. |
| `POST /api/search` | HTTP-level with mocked `semantic_search`. Test: 503 on embed failure. Test: 422 on empty query. Test: `fallback_used` flag propagated. |

---

## 11. Out of Scope for M3

- Anomaly scoring on ingestion (M5)
- `GET /api/correlate/{trace_id}` (M4)
- LLM root cause analysis (M4)
- `audit_log` table (M6)
- Auth (`X-API-Key`) enforcement (M6)
