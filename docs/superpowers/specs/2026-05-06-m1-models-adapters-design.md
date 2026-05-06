# LogIQ M1 — Data Models & Source Adapters Design

**Date:** 2026-05-06
**Milestone:** M1 — Data Models & Source Adapters
**Status:** Approved
**Scope:** Pydantic v2 schemas for every data entity + BaseSourceAdapter ABC + LokiAdapter (poll + stream)

---

## 1. Objective

Define the canonical data contracts that every subsequent milestone builds on, and deliver a working `LokiAdapter` that can ingest logs from the running Loki instance. M1 has no external side effects in the API — it is purely a library layer consumed by M2 (Sync Engine).

---

## 2. Data Models (`models/`)

Four Pydantic v2 models cover every entity in the system. All IDs are UUID4 strings (not UUIDs) for easy JSON serialisation.

### 2.1 LogEvent

The canonical, normalised log entry emitted by every source adapter.

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | `str` | `uuid4()` | Auto-generated |
| `timestamp` | `datetime` | required | Timezone-aware |
| `severity` | `SeverityLevel` | required | Enum: ERROR/WARN/INFO/DEBUG/TRACE/UNKNOWN |
| `service` | `str` | required | Source service name |
| `environment` | `str` | required | e.g. "production" |
| `trace_id` | `str \| None` | `None` | Cross-service correlation |
| `span_id` | `str \| None` | `None` | Individual span |
| `message` | `str` | required | Human-readable log line |
| `metadata` | `dict[str, Any]` | `{}` | Structured context |
| `raw` | `dict[str, Any]` | `{}` | Original log payload (verbatim) |
| `source` | `str` | required | Adapter name, e.g. "loki" |

**`SeverityLevel` enum:** `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`, `UNKNOWN`. Declared as `str` enum so JSON serialisation produces the string value directly.

### 2.2 RootCauseAnalysis

LLM-generated analysis of an error cluster. Created by the intelligence layer (M5), stored in the `rca` table.

| Field | Type | Default |
|---|---|---|
| `id` | `str` | `uuid4()` |
| `log_id` | `str` | required |
| `trace_id` | `str \| None` | `None` |
| `summary` | `str` | required |
| `root_cause` | `str` | required |
| `affected_services` | `list[str]` | `[]` |
| `confidence` | `float` (0.0–1.0) | required |
| `suggested_fixes` | `list[str]` | `[]` |
| `created_at` | `datetime` | `now(UTC)` |

### 2.3 ActionableTask

Human-approvable task generated from an RCA. Human approval is enforced at the DB level — `status` must be `approved` before any agent acts on it.

| Field | Type | Default |
|---|---|---|
| `id` | `str` | `uuid4()` |
| `rca_id` | `str` | required |
| `log_id` | `str` | required |
| `title` | `str` | required |
| `description` | `str` | required |
| `status` | `TaskStatus` | `pending` |
| `priority` | `TaskPriority` | `medium` |
| `agent_id` | `str \| None` | `None` (v2.0) |
| `created_at` | `datetime` | `now(UTC)` |
| `updated_at` | `datetime` | `now(UTC)` |

**`TaskStatus` enum:** `pending → approved → in_progress → resolved` or `dismissed`.

**`TaskPriority` enum:** `low`, `medium`, `high`, `critical`.

### 2.4 AnomalyResult

KNN-based anomaly detection result from the ingestion pipeline (M2/M4).

| Field | Type | Default |
|---|---|---|
| `id` | `str` | `uuid4()` |
| `log_id` | `str` | required |
| `score` | `float` (0.0–1.0) | required |
| `is_anomaly` | `bool` | required |
| `threshold` | `float` | required |
| `reviewed` | `bool` | `False` |
| `detected_at` | `datetime` | `now(UTC)` |

Note: `is_anomaly` is set by the caller (`score < threshold`). Not computed automatically by the model — the caller controls the threshold comparison.

---

## 3. Source Adapter Layer (`adapters/`)

### 3.1 BaseSourceAdapter ABC

Defines the 5-method contract that every log source must implement. Adding a new source requires only: implementing these 5 methods + 1 config entry in `config.yaml`.

```
BaseSourceAdapter (ABC)
├── fetch_logs(start, end, limit) → list[LogEvent]   # poll mode
├── stream_logs() → AsyncIterator[LogEvent]           # stream mode (async generator)
├── health_check() → dict                             # {"status": "ok"|"error", "detail": str}
├── get_source_name() → str                           # "loki", "datadog", etc.
└── normalise(raw: dict) → LogEvent                   # source-specific parsing
```

`fetch_logs` and `health_check` are `async def`. `stream_logs` is declared as a non-async abstract method returning `AsyncIterator[LogEvent]`; concrete implementations are async generators. `get_source_name` and `normalise` are synchronous.

### 3.2 LokiAdapter

Implements `BaseSourceAdapter` against Loki's HTTP and WebSocket APIs.

**Poll mode — `fetch_logs()`:**
```
GET /loki/api/v1/query_range
  ?query={environment="production"}
  &start=<unix_ns>
  &end=<unix_ns>
  &limit=100
  &direction=backward
```

Response:
```json
{
  "data": {
    "result": [
      {
        "stream": {"service": "auth-service", "severity": "ERROR"},
        "values": [["<ts_ns>", "<json_string>"]]
      }
    ]
  }
}
```

Each `<json_string>` is the structured JSON from the log generator — parsed by `normalise()`.

**Stream mode — `stream_logs()`:**
```
WebSocket: ws://loki:3100/loki/api/v1/tail?query=<url-encoded-query>
```

Messages arrive continuously; each has the same `streams[].values` structure as the query response.

**Health — `health_check()`:**
```
GET /ready  → 200 text "ready"
```

**`normalise()` mapping:**

| Loki JSON field | LogEvent field |
|---|---|
| `timestamp` | `timestamp` (via `datetime.fromisoformat`) |
| `severity` | `severity` (mapped to SeverityLevel; unknown values → `UNKNOWN`) |
| `service` | `service` |
| `environment` | `environment` |
| `trace_id` | `trace_id` (optional) |
| `span_id` | `span_id` (optional) |
| `message` | `message` |
| `metadata` | `metadata` |
| *(full dict)* | `raw` |
| *(adapter name)* | `source` |

---

## 4. Directory Layout After M1

```
models/
├── __init__.py      # re-exports: LogEvent, SeverityLevel, RootCauseAnalysis,
│                    #             ActionableTask, TaskStatus, TaskPriority, AnomalyResult
├── log_event.py     # SeverityLevel enum + LogEvent
├── rca.py           # RootCauseAnalysis
├── task.py          # TaskStatus, TaskPriority enums + ActionableTask
└── anomaly.py       # AnomalyResult

adapters/
├── __init__.py      # re-exports: BaseSourceAdapter, LokiAdapter
├── base.py          # BaseSourceAdapter ABC
└── loki.py          # LokiAdapter

tests/
├── models/
│   ├── __init__.py
│   ├── test_log_event.py           # 12 tests
│   └── test_supporting_models.py   # 10 tests
└── adapters/
    ├── __init__.py
    ├── test_base.py                # 3 tests — ABC enforcement
    └── test_loki.py                # 15 tests — normalise, fetch, health, stream
```

Total new tests: ~40. All pass without a live Loki instance.

---

## 5. New Dependencies

| Package | Version | Reason |
|---|---|---|
| `pydantic` | `2.9.2` | Explicit pin — already transitive via FastAPI |
| `websockets` | `12.0` | Loki WebSocket tail endpoint |
| `pytest-mock` | `3.14.0` | Cleaner mock fixtures in adapter tests |

---

## 6. Definition of Done

- [ ] `pytest` passes: all pre-existing 17 tests + ~40 new M1 tests
- [ ] `from models import LogEvent, RootCauseAnalysis, ActionableTask, AnomalyResult` works
- [ ] `from adapters import LokiAdapter` works
- [ ] `LokiAdapter("http://loki:3100").normalise(raw_dict)` returns a valid `LogEvent`
- [ ] `LokiAdapter.fetch_logs()` correctly parses a Loki `query_range` response
- [ ] `LokiAdapter.health_check()` returns `{"status": "ok", ...}` on 200
- [ ] `LokiAdapter.stream_logs()` is an async generator
- [ ] No circular imports between `models/` and `adapters/`
