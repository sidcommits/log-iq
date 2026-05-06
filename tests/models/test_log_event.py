from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

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
    with pytest.raises(ValidationError):
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


def test_timestamp_must_be_timezone_aware():
    from datetime import datetime
    with pytest.raises(ValidationError):
        _make(timestamp=datetime(2026, 5, 6, 10, 0, 0))  # no tzinfo


def test_log_event_is_immutable():
    from pydantic import ValidationError
    event = _make()
    with pytest.raises(ValidationError):
        event.message = "tampered"
