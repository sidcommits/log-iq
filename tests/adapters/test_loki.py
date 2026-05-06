import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
