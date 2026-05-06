# LogIQ M1 — Data Models & Source Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement canonical Pydantic v2 data models (`LogEvent`, `RootCauseAnalysis`, `ActionableTask`, `AnomalyResult`) and a working `LokiAdapter` that polls and streams logs from Loki, normalising each entry into a `LogEvent`.

**Architecture:** Two independent subsystems: (1) `models/` — Pydantic v2 schemas that define the data contract for every layer; (2) `adapters/` — a `BaseSourceAdapter` ABC (5 abstract methods) plus a concrete `LokiAdapter` that talks to Loki's HTTP query and WebSocket tail APIs. All unit tests run without a live Loki instance — HTTP calls are mocked via `unittest.mock`.

**Tech Stack:** Python 3.12, Pydantic 2.9.2, httpx 0.27.2, websockets 12.0, pytest 8.3.2, pytest-asyncio 0.24.0, pytest-mock 3.14.0.

---

## File Map

| File | Created/Modified | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add `pydantic`, `websockets`, `pytest-mock` |
| `models/log_event.py` | Create | `SeverityLevel` enum + `LogEvent` model |
| `models/rca.py` | Create | `RootCauseAnalysis` model |
| `models/task.py` | Create | `TaskStatus`, `TaskPriority` enums + `ActionableTask` model |
| `models/anomaly.py` | Create | `AnomalyResult` model |
| `models/__init__.py` | Modify | Re-export all models and enums |
| `adapters/base.py` | Create | `BaseSourceAdapter` ABC — 5 abstract methods |
| `adapters/loki.py` | Create | `LokiAdapter` (HTTP poll + WebSocket stream) |
| `adapters/__init__.py` | Modify | Re-export `BaseSourceAdapter`, `LokiAdapter` |
| `tests/models/__init__.py` | Create | Empty package |
| `tests/models/test_log_event.py` | Create | `LogEvent` + `SeverityLevel` tests (12 tests) |
| `tests/models/test_supporting_models.py` | Create | RCA, Task, Anomaly tests (10 tests) |
| `tests/adapters/__init__.py` | Create | Empty package |
| `tests/adapters/test_base.py` | Create | ABC contract enforcement (3 tests) |
| `tests/adapters/test_loki.py` | Create | `LokiAdapter` unit tests, mocked HTTP (15 tests) |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update `requirements.txt`**

Replace the entire file with:

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
prometheus-fastapi-instrumentator==7.0.0
pyyaml==6.0.2
httpx==0.27.2
pydantic==2.9.2
websockets==12.0
pytest==8.3.2
pytest-asyncio==0.24.0
pytest-mock==3.14.0
```

- [ ] **Step 2: Install new dependencies**

```bash
pip install pydantic==2.9.2 websockets==12.0 pytest-mock==3.14.0
```

Expected: all three install without errors.

- [ ] **Step 3: Create test package directories**

```bash
mkdir -p tests/models tests/adapters
touch tests/models/__init__.py tests/adapters/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt tests/models/__init__.py tests/adapters/__init__.py
git commit -m "chore: add pydantic, websockets, pytest-mock to M1 dependencies"
```

---

## Task 2: LogEvent Pydantic Model (TDD)

**Files:**
- Create: `tests/models/test_log_event.py`
- Create: `models/log_event.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/models/test_log_event.py`:

```python
from datetime import datetime, timezone

import pytest

from models.log_event import LogEvent, SeverityLevel


def _make(**kwargs) -> LogEvent:
    defaults = {
        "timestamp": datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        "severity": SeverityLevel.INFO,
        "service": "auth-service",
        "environment": "production",
        "message": "user login successful",
        "source": "loki",
    }
    return LogEvent(**{**defaults, **kwargs})


def test_log_event_creation_with_required_fields():
    event = _make()
    assert event.severity == SeverityLevel.INFO
    assert event.service == "auth-service"
    assert event.environment == "production"
    assert event.message == "user login successful"
    assert event.source == "loki"


def test_log_event_id_auto_generated():
    event = _make()
    assert event.id is not None
    assert len(event.id) == 36  # UUID4 canonical string


def test_log_event_ids_are_unique():
    e1 = _make()
    e2 = _make()
    assert e1.id != e2.id


def test_log_event_trace_id_defaults_to_none():
    assert _make().trace_id is None


def test_log_event_span_id_defaults_to_none():
    assert _make().span_id is None


def test_log_event_metadata_defaults_to_empty_dict():
    assert _make().metadata == {}


def test_log_event_raw_defaults_to_empty_dict():
    assert _make().raw == {}


def test_log_event_severity_accepts_all_levels():
    for level in ("ERROR", "WARN", "INFO", "DEBUG", "TRACE", "UNKNOWN"):
        event = _make(severity=SeverityLevel(level))
        assert event.severity.value == level


def test_log_event_severity_rejects_invalid_string():
    with pytest.raises(Exception):
        _make(severity="CRITICAL")  # not a valid SeverityLevel


def test_log_event_with_all_optional_fields():
    event = _make(
        trace_id="abc123def456",
        span_id="12345678",
        metadata={"pool_size": 10},
        raw={"original": "payload"},
    )
    assert event.trace_id == "abc123def456"
    assert event.span_id == "12345678"
    assert event.metadata["pool_size"] == 10
    assert event.raw["original"] == "payload"


def test_log_event_model_dump_round_trip():
    original = _make(trace_id="t1", metadata={"k": "v"})
    data = original.model_dump()
    restored = LogEvent(**data)
    assert restored.id == original.id
    assert restored.trace_id == "t1"
    assert restored.metadata == {"k": "v"}


def test_severity_level_is_str_enum():
    assert SeverityLevel.ERROR == "ERROR"
    assert isinstance(SeverityLevel.ERROR, str)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/models/test_log_event.py -v
```

Expected: `ModuleNotFoundError: No module named 'models.log_event'`

- [ ] **Step 3: Create `models/log_event.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"
    UNKNOWN = "UNKNOWN"


class LogEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    severity: SeverityLevel
    service: str
    environment: str
    trace_id: str | None = None
    span_id: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    source: str
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
pytest tests/models/test_log_event.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add models/log_event.py tests/models/test_log_event.py
git commit -m "feat: LogEvent Pydantic model with SeverityLevel enum"
```

---

## Task 3: Supporting Models — RCA, Task, Anomaly (TDD)

**Files:**
- Create: `tests/models/test_supporting_models.py`
- Create: `models/rca.py`
- Create: `models/task.py`
- Create: `models/anomaly.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/models/test_supporting_models.py`:

```python
import pytest


# ── RootCauseAnalysis ──────────────────────────────────────────────────────────

def test_rca_creation_with_required_fields():
    from models.rca import RootCauseAnalysis
    rca = RootCauseAnalysis(
        log_id="log-abc",
        summary="DB connection pool exhausted",
        root_cause="max_connections reached under high load",
        confidence=0.92,
    )
    assert rca.log_id == "log-abc"
    assert rca.confidence == 0.92
    assert rca.affected_services == []
    assert rca.suggested_fixes == []
    assert rca.trace_id is None


def test_rca_id_auto_generated():
    from models.rca import RootCauseAnalysis
    rca = RootCauseAnalysis(log_id="x", summary="s", root_cause="r", confidence=0.5)
    assert len(rca.id) == 36


def test_rca_confidence_rejects_above_one():
    from models.rca import RootCauseAnalysis
    with pytest.raises(Exception):
        RootCauseAnalysis(log_id="x", summary="s", root_cause="r", confidence=1.5)


def test_rca_confidence_rejects_below_zero():
    from models.rca import RootCauseAnalysis
    with pytest.raises(Exception):
        RootCauseAnalysis(log_id="x", summary="s", root_cause="r", confidence=-0.1)


def test_rca_with_services_and_fixes():
    from models.rca import RootCauseAnalysis
    rca = RootCauseAnalysis(
        log_id="log-1",
        summary="auth spike",
        root_cause="brute force attack",
        confidence=0.85,
        affected_services=["auth-service", "api-gateway"],
        suggested_fixes=["rate limit by IP", "enable account lockout"],
    )
    assert "auth-service" in rca.affected_services
    assert len(rca.suggested_fixes) == 2


# ── ActionableTask ─────────────────────────────────────────────────────────────

def test_task_creation_with_required_fields():
    from models.task import ActionableTask, TaskStatus, TaskPriority
    task = ActionableTask(
        rca_id="rca-1",
        log_id="log-1",
        title="Fix connection pool",
        description="Increase max_connections in postgres config",
    )
    assert task.title == "Fix connection pool"
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.MEDIUM
    assert task.agent_id is None


def test_task_status_transitions():
    from models.task import ActionableTask, TaskStatus
    for status in ("pending", "approved", "in_progress", "resolved", "dismissed"):
        task = ActionableTask(
            rca_id="r", log_id="l", title="t", description="d",
            status=TaskStatus(status),
        )
        assert task.status.value == status


def test_task_priority_enum_values():
    from models.task import ActionableTask, TaskPriority
    for priority in ("low", "medium", "high", "critical"):
        task = ActionableTask(
            rca_id="r", log_id="l", title="t", description="d",
            priority=TaskPriority(priority),
        )
        assert task.priority.value == priority


def test_task_id_auto_generated():
    from models.task import ActionableTask
    task = ActionableTask(rca_id="r", log_id="l", title="t", description="d")
    assert len(task.id) == 36


# ── AnomalyResult ──────────────────────────────────────────────────────────────

def test_anomaly_creation():
    from models.anomaly import AnomalyResult
    anomaly = AnomalyResult(log_id="log-1", score=0.45, is_anomaly=True, threshold=0.72)
    assert anomaly.score == 0.45
    assert anomaly.is_anomaly is True
    assert anomaly.reviewed is False
    assert anomaly.threshold == 0.72


def test_anomaly_id_auto_generated():
    from models.anomaly import AnomalyResult
    anomaly = AnomalyResult(log_id="x", score=0.5, is_anomaly=False, threshold=0.72)
    assert len(anomaly.id) == 36


def test_anomaly_score_rejects_above_one():
    from models.anomaly import AnomalyResult
    with pytest.raises(Exception):
        AnomalyResult(log_id="x", score=1.5, is_anomaly=True, threshold=0.72)


def test_anomaly_score_rejects_below_zero():
    from models.anomaly import AnomalyResult
    with pytest.raises(Exception):
        AnomalyResult(log_id="x", score=-0.1, is_anomaly=True, threshold=0.72)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/models/test_supporting_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'models.rca'`

- [ ] **Step 3: Create `models/rca.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class RootCauseAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_id: str
    trace_id: str | None = None
    summary: str
    root_cause: str
    affected_services: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_fixes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Create `models/task.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionableTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rca_id: str
    log_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    agent_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 5: Create `models/anomaly.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AnomalyResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_id: str
    score: float = Field(ge=0.0, le=1.0)
    is_anomaly: bool
    threshold: float
    reviewed: bool = False
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 6: Run tests — confirm they pass**

```bash
pytest tests/models/test_supporting_models.py -v
```

Expected: 12 passed.

- [ ] **Step 7: Run full suite — confirm nothing broke**

```bash
pytest -v
```

Expected: 29 passed (17 pre-existing + 12 LogEvent + 12 supporting — total may vary by 1 depending on shared count).

- [ ] **Step 8: Commit**

```bash
git add models/rca.py models/task.py models/anomaly.py tests/models/test_supporting_models.py
git commit -m "feat: RootCauseAnalysis, ActionableTask, AnomalyResult Pydantic models"
```

---

## Task 4: Update models/__init__.py

**Files:**
- Modify: `models/__init__.py`

- [ ] **Step 1: Update `models/__init__.py`**

```python
from models.log_event import LogEvent, SeverityLevel
from models.rca import RootCauseAnalysis
from models.task import ActionableTask, TaskPriority, TaskStatus
from models.anomaly import AnomalyResult

__all__ = [
    "LogEvent",
    "SeverityLevel",
    "RootCauseAnalysis",
    "ActionableTask",
    "TaskStatus",
    "TaskPriority",
    "AnomalyResult",
]
```

- [ ] **Step 2: Verify imports work from top-level**

```bash
python -c "from models import LogEvent, RootCauseAnalysis, ActionableTask, AnomalyResult; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add models/__init__.py
git commit -m "chore: re-export all models from models/__init__.py"
```

---

## Task 5: BaseSourceAdapter ABC (TDD)

**Files:**
- Create: `tests/adapters/test_base.py`
- Create: `adapters/base.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/adapters/test_base.py`:

```python
import pytest
from adapters.base import BaseSourceAdapter


def test_base_adapter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseSourceAdapter()


def test_partial_implementation_raises_on_instantiation():
    class OnlyName(BaseSourceAdapter):
        def get_source_name(self) -> str:
            return "partial"

    with pytest.raises(TypeError):
        OnlyName()


def test_full_implementation_instantiates_successfully():
    from datetime import datetime
    from collections.abc import AsyncIterator
    from models.log_event import LogEvent

    class StubAdapter(BaseSourceAdapter):
        async def fetch_logs(
            self, start: datetime, end: datetime, limit: int = 100
        ) -> list[LogEvent]:
            return []

        async def stream_logs(self) -> AsyncIterator[LogEvent]:
            return
            yield  # unreachable — marks this as an async generator

        async def health_check(self) -> dict:
            return {"status": "ok", "detail": "stub"}

        def get_source_name(self) -> str:
            return "stub"

        def normalise(self, raw: dict) -> LogEvent:
            raise NotImplementedError

    adapter = StubAdapter()
    assert adapter.get_source_name() == "stub"
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/adapters/test_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'adapters.base'`

- [ ] **Step 3: Create `adapters/base.py`**

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from models.log_event import LogEvent


class BaseSourceAdapter(ABC):

    @abstractmethod
    async def fetch_logs(
        self, start: datetime, end: datetime, limit: int = 100
    ) -> list[LogEvent]:
        """Poll for logs between start and end. Returns up to limit events."""
        ...

    @abstractmethod
    def stream_logs(self) -> AsyncIterator[LogEvent]:
        """Real-time stream. Concrete implementations are async generators.
        Usage: async for event in adapter.stream_logs(): ..."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Check source availability. Returns {"status": "ok"|"error", "detail": str}."""
        ...

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the configured source name, e.g. "loki"."""
        ...

    @abstractmethod
    def normalise(self, raw: dict) -> LogEvent:
        """Convert a raw source log entry dict to a normalised LogEvent."""
        ...
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
pytest tests/adapters/test_base.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add adapters/base.py tests/adapters/test_base.py
git commit -m "feat: BaseSourceAdapter ABC with 5-method contract"
```

---

## Task 6: LokiAdapter — normalise() and get_source_name() (TDD)

**Files:**
- Create: `tests/adapters/test_loki.py` (normalise + get_source_name tests only)
- Create: `adapters/loki.py` (normalise + get_source_name only)

- [ ] **Step 1: Write the failing tests**

Create `tests/adapters/test_loki.py` with normalise and name tests:

```python
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.loki import LokiAdapter
from models.log_event import SeverityLevel


# ── helpers ───────────────────────────────────────────────────────────────────

def _raw(**kwargs) -> dict:
    """Minimal valid raw log dict from the log generator."""
    defaults = {
        "timestamp": "2026-05-06T10:00:00+00:00",
        "severity": "ERROR",
        "service": "auth-service",
        "environment": "production",
        "trace_id": "abc123def456",
        "span_id": "12345678",
        "message": "connection pool exhausted",
        "metadata": {"pool_size": 10},
    }
    return {**defaults, **kwargs}


# ── get_source_name ────────────────────────────────────────────────────────────

def test_get_source_name_defaults_to_loki():
    adapter = LokiAdapter(url="http://loki:3100")
    assert adapter.get_source_name() == "loki"


def test_get_source_name_returns_custom_name():
    adapter = LokiAdapter(url="http://loki:3100", name="prod-loki")
    assert adapter.get_source_name() == "prod-loki"


# ── normalise ─────────────────────────────────────────────────────────────────

def test_normalise_maps_all_fields():
    adapter = LokiAdapter(url="http://loki:3100")
    event = adapter.normalise(_raw())
    assert event.severity == SeverityLevel.ERROR
    assert event.service == "auth-service"
    assert event.environment == "production"
    assert event.trace_id == "abc123def456"
    assert event.span_id == "12345678"
    assert event.message == "connection pool exhausted"
    assert event.metadata["pool_size"] == 10
    assert event.source == "loki"


def test_normalise_sets_source_to_adapter_name():
    adapter = LokiAdapter(url="http://loki:3100", name="prod-loki")
    event = adapter.normalise(_raw())
    assert event.source == "prod-loki"


def test_normalise_stores_raw_dict():
    adapter = LokiAdapter(url="http://loki:3100")
    raw = _raw()
    event = adapter.normalise(raw)
    assert event.raw == raw


def test_normalise_falls_back_to_unknown_severity():
    adapter = LokiAdapter(url="http://loki:3100")
    event = adapter.normalise(_raw(severity="CRITICAL"))  # not in SeverityLevel
    assert event.severity == SeverityLevel.UNKNOWN


def test_normalise_handles_missing_trace_id():
    adapter = LokiAdapter(url="http://loki:3100")
    raw = _raw()
    del raw["trace_id"]
    event = adapter.normalise(raw)
    assert event.trace_id is None


def test_normalise_handles_missing_span_id():
    adapter = LokiAdapter(url="http://loki:3100")
    raw = _raw()
    del raw["span_id"]
    event = adapter.normalise(raw)
    assert event.span_id is None


def test_normalise_handles_missing_metadata():
    adapter = LokiAdapter(url="http://loki:3100")
    raw = _raw()
    del raw["metadata"]
    event = adapter.normalise(raw)
    assert event.metadata == {}


def test_normalise_parses_timestamp_as_utc_datetime():
    adapter = LokiAdapter(url="http://loki:3100")
    event = adapter.normalise(_raw(timestamp="2026-05-06T10:00:00+00:00"))
    assert event.timestamp == datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/adapters/test_loki.py -v
```

Expected: `ModuleNotFoundError: No module named 'adapters.loki'`

- [ ] **Step 3: Create `adapters/loki.py`** (normalise + get_source_name only — fetch/health/stream added next)

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import quote

import httpx
import websockets

from adapters.base import BaseSourceAdapter
from models.log_event import LogEvent, SeverityLevel


class LokiAdapter(BaseSourceAdapter):
    def __init__(
        self,
        url: str,
        name: str = "loki",
        query: str = '{environment="production"}',
    ) -> None:
        self._url = url.rstrip("/")
        self._name = name
        self._query = query

    # ── BaseSourceAdapter interface ────────────────────────────────────────────

    def get_source_name(self) -> str:
        return self._name

    def normalise(self, raw: dict) -> LogEvent:
        severity_str = raw.get("severity", "UNKNOWN").upper()
        try:
            severity = SeverityLevel(severity_str)
        except ValueError:
            severity = SeverityLevel.UNKNOWN

        return LogEvent(
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

    async def fetch_logs(
        self, start: datetime, end: datetime, limit: int = 100
    ) -> list[LogEvent]:
        raise NotImplementedError("implemented in Task 7")

    def stream_logs(self) -> AsyncIterator[LogEvent]:
        raise NotImplementedError("implemented in Task 9")

    async def health_check(self) -> dict:
        raise NotImplementedError("implemented in Task 8")
```

- [ ] **Step 4: Run normalise + name tests — confirm they pass**

```bash
pytest tests/adapters/test_loki.py -k "normalise or source_name" -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add adapters/loki.py tests/adapters/test_loki.py
git commit -m "feat: LokiAdapter normalise() and get_source_name()"
```

---

## Task 7: LokiAdapter — fetch_logs() (TDD)

**Files:**
- Modify: `tests/adapters/test_loki.py` (append fetch_logs tests)
- Modify: `adapters/loki.py` (implement fetch_logs)

- [ ] **Step 1: Append fetch_logs tests to `tests/adapters/test_loki.py`**

Add these functions at the end of the file:

```python
# ── fetch_logs ────────────────────────────────────────────────────────────────

def _loki_response(log_dicts: list[dict]) -> MagicMock:
    """Build a mock httpx response with Loki query_range shape."""
    values = [
        ["1746518400000000000", json.dumps(d)]
        for d in log_dicts
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "streams",
            "result": [
                {
                    "stream": {"service": "auth-service", "severity": "ERROR"},
                    "values": values,
                }
            ],
        },
    }
    return mock_resp


@pytest.mark.asyncio
async def test_fetch_logs_returns_log_events():
    adapter = LokiAdapter(url="http://loki:3100")
    mock_resp = _loki_response([_raw()])

    with patch("adapters.loki.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        events = await adapter.fetch_logs(
            start=datetime(2026, 5, 6, 0, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc),
        )

    assert len(events) == 1
    assert events[0].severity == SeverityLevel.ERROR
    assert events[0].service == "auth-service"
    assert events[0].message == "connection pool exhausted"


@pytest.mark.asyncio
async def test_fetch_logs_calls_query_range_endpoint():
    adapter = LokiAdapter(url="http://loki:3100")
    mock_resp = _loki_response([_raw()])

    with patch("adapters.loki.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        await adapter.fetch_logs(
            start=datetime(2026, 5, 6, 0, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc),
            limit=50,
        )

    call_kwargs = mock_client.get.call_args
    assert "/loki/api/v1/query_range" in call_kwargs.args[0]
    assert call_kwargs.kwargs["params"]["limit"] == 50


@pytest.mark.asyncio
async def test_fetch_logs_skips_malformed_json():
    adapter = LokiAdapter(url="http://loki:3100")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "result": [
                {
                    "stream": {},
                    "values": [
                        ["1234", "not-valid-json"],
                        ["1235", json.dumps(_raw(message="valid"))],
                    ],
                }
            ]
        }
    }

    with patch("adapters.loki.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        events = await adapter.fetch_logs(
            start=datetime(2026, 5, 6, 0, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc),
        )

    assert len(events) == 1
    assert events[0].message == "valid"


@pytest.mark.asyncio
async def test_fetch_logs_returns_empty_list_for_no_results():
    adapter = LokiAdapter(url="http://loki:3100")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": {"result": []}}

    with patch("adapters.loki.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        events = await adapter.fetch_logs(
            start=datetime(2026, 5, 6, 0, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc),
        )

    assert events == []
```

- [ ] **Step 2: Run new tests — confirm they fail**

```bash
pytest tests/adapters/test_loki.py -k "fetch_logs" -v
```

Expected: `NotImplementedError: implemented in Task 7`

- [ ] **Step 3: Implement `fetch_logs` in `adapters/loki.py`**

Replace the `fetch_logs` stub with:

```python
    async def fetch_logs(
        self, start: datetime, end: datetime, limit: int = 100
    ) -> list[LogEvent]:
        start_ns = int(start.timestamp() * 1_000_000_000)
        end_ns = int(end.timestamp() * 1_000_000_000)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._url}/loki/api/v1/query_range",
                params={
                    "query": self._query,
                    "start": start_ns,
                    "end": end_ns,
                    "limit": limit,
                    "direction": "backward",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        events: list[LogEvent] = []
        for stream in data.get("data", {}).get("result", []):
            for _ts, log_line in stream.get("values", []):
                try:
                    raw = json.loads(log_line)
                    events.append(self.normalise(raw))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        return events
```

- [ ] **Step 4: Run fetch_logs tests — confirm they pass**

```bash
pytest tests/adapters/test_loki.py -k "fetch_logs" -v
```

Expected: 4 passed.

- [ ] **Step 5: Run all adapter tests — confirm nothing broke**

```bash
pytest tests/adapters/ -v
```

Expected: all passing (normalise + name + fetch_logs tests).

- [ ] **Step 6: Commit**

```bash
git add adapters/loki.py tests/adapters/test_loki.py
git commit -m "feat: LokiAdapter.fetch_logs() with Loki query_range HTTP polling"
```

---

## Task 8: LokiAdapter — health_check() (TDD)

**Files:**
- Modify: `tests/adapters/test_loki.py` (append health_check tests)
- Modify: `adapters/loki.py` (implement health_check)

- [ ] **Step 1: Append health_check tests to `tests/adapters/test_loki.py`**

```python
# ── health_check ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_returns_ok_on_200():
    adapter = LokiAdapter(url="http://loki:3100")
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("adapters.loki.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        result = await adapter.health_check()

    assert result["status"] == "ok"
    assert "detail" in result


@pytest.mark.asyncio
async def test_health_check_returns_error_on_non_200():
    adapter = LokiAdapter(url="http://loki:3100")
    mock_resp = MagicMock()
    mock_resp.status_code = 503

    with patch("adapters.loki.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        result = await adapter.health_check()

    assert result["status"] == "error"
    assert "503" in result["detail"]


@pytest.mark.asyncio
async def test_health_check_returns_error_on_connection_failure():
    adapter = LokiAdapter(url="http://loki:3100")

    with patch("adapters.loki.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        MockClient.return_value = mock_client

        result = await adapter.health_check()

    assert result["status"] == "error"
    assert "refused" in result["detail"]
```

You also need to add `import httpx` to the test file's top-level imports. The existing import block at the top of `tests/adapters/test_loki.py` should read:

```python
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from adapters.loki import LokiAdapter
from models.log_event import SeverityLevel
```

- [ ] **Step 2: Run new tests — confirm they fail**

```bash
pytest tests/adapters/test_loki.py -k "health_check" -v
```

Expected: `NotImplementedError: implemented in Task 8`

- [ ] **Step 3: Implement `health_check` in `adapters/loki.py`**

Replace the `health_check` stub with:

```python
    async def health_check(self) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._url}/ready", timeout=5.0)
                if resp.status_code == 200:
                    return {"status": "ok", "detail": "Loki is ready"}
                return {"status": "error", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
```

- [ ] **Step 4: Run health_check tests — confirm they pass**

```bash
pytest tests/adapters/test_loki.py -k "health_check" -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add adapters/loki.py tests/adapters/test_loki.py
git commit -m "feat: LokiAdapter.health_check() with /ready ping"
```

---

## Task 9: LokiAdapter — stream_logs() (TDD + Implementation)

**Files:**
- Modify: `tests/adapters/test_loki.py` (append stream_logs test)
- Modify: `adapters/loki.py` (implement stream_logs)

- [ ] **Step 1: Append stream_logs structural test**

```python
# ── stream_logs ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_logs_is_async_generator():
    import inspect
    adapter = LokiAdapter(url="http://loki:3100")
    gen = adapter.stream_logs()
    assert inspect.isasyncgen(gen)
    await gen.aclose()
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
pytest tests/adapters/test_loki.py -k "stream_logs" -v
```

Expected: `NotImplementedError: implemented in Task 9`

- [ ] **Step 3: Implement `stream_logs` in `adapters/loki.py`**

Replace the `stream_logs` stub with:

```python
    async def stream_logs(self) -> AsyncIterator[LogEvent]:
        ws_url = (
            self._url
            .replace("http://", "ws://")
            .replace("https://", "wss://")
        )
        uri = f"{ws_url}/loki/api/v1/tail?query={quote(self._query)}"
        async with websockets.connect(uri) as ws:
            async for message in ws:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue
                for stream in data.get("streams", []):
                    for _ts, log_line in stream.get("values", []):
                        try:
                            raw = json.loads(log_line)
                            yield self.normalise(raw)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
```

- [ ] **Step 4: Run stream_logs test — confirm it passes**

```bash
pytest tests/adapters/test_loki.py -k "stream_logs" -v
```

Expected: 1 passed.

- [ ] **Step 5: Run all adapter tests**

```bash
pytest tests/adapters/ -v
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add adapters/loki.py tests/adapters/test_loki.py
git commit -m "feat: LokiAdapter.stream_logs() WebSocket tail via websockets library"
```

---

## Task 10: Wire adapters/__init__.py and Final Verification

**Files:**
- Modify: `adapters/__init__.py`

- [ ] **Step 1: Update `adapters/__init__.py`**

```python
from adapters.base import BaseSourceAdapter
from adapters.loki import LokiAdapter

__all__ = ["BaseSourceAdapter", "LokiAdapter"]
```

- [ ] **Step 2: Verify top-level imports work**

```bash
python -c "from adapters import BaseSourceAdapter, LokiAdapter; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify no circular imports**

```bash
python -c "from models import LogEvent; from adapters import LokiAdapter; print('no circular imports')"
```

Expected: `no circular imports`

- [ ] **Step 4: Run the complete test suite**

```bash
pytest -v
```

Expected: all tests pass. Approximate count: 17 (pre-existing M0) + 12 (LogEvent) + 12 (supporting models) + 3 (BaseSourceAdapter) + 15 (LokiAdapter) = ~59 passed.

- [ ] **Step 5: Verify normalise works end-to-end with a real dict**

```bash
python -c "
from adapters import LokiAdapter
from datetime import datetime, timezone

adapter = LokiAdapter('http://loki:3100')
event = adapter.normalise({
    'timestamp': '2026-05-06T10:00:00+00:00',
    'severity': 'ERROR',
    'service': 'auth-service',
    'environment': 'production',
    'trace_id': 'abc123',
    'span_id': 'def456',
    'message': 'connection pool exhausted',
    'metadata': {'pool_size': 10},
})
print(f'severity={event.severity}, service={event.service}, source={event.source}')
"
```

Expected: `severity=ERROR, service=auth-service, source=loki`

- [ ] **Step 6: Commit**

```bash
git add adapters/__init__.py
git commit -m "chore: re-export BaseSourceAdapter and LokiAdapter from adapters/__init__.py"
```

---

## Definition of Done

- [ ] `pytest` passes: all pre-existing 17 tests + ~40 new M1 tests
- [ ] `from models import LogEvent, RootCauseAnalysis, ActionableTask, AnomalyResult` works
- [ ] `from adapters import BaseSourceAdapter, LokiAdapter` works
- [ ] `LokiAdapter("http://loki:3100").normalise(raw_dict)` returns a valid `LogEvent`
- [ ] `LokiAdapter.fetch_logs()` correctly parses Loki's `query_range` response format
- [ ] `LokiAdapter.health_check()` returns `{"status": "ok", ...}` on 200, `{"status": "error", ...}` otherwise
- [ ] `LokiAdapter.stream_logs()` is an async generator (confirmed by `inspect.isasyncgen`)
- [ ] No circular imports between `models/` and `adapters/`
