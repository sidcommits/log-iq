import json
import random
import time

import pytest


def test_make_log_event_required_fields():
    from tools.log_generator.generator import make_log_event
    event = make_log_event("auth-service", "ERROR", "test message")
    assert event["severity"] == "ERROR"
    assert event["service"] == "auth-service"
    assert event["environment"] == "production"
    assert event["message"] == "test message"
    assert "timestamp" in event
    assert "trace_id" in event
    assert "span_id" in event
    assert isinstance(event["metadata"], dict)


def test_make_log_event_uses_provided_trace_id():
    from tools.log_generator.generator import make_log_event
    event = make_log_event("auth-service", "ERROR", "test", trace_id="abc123fixed")
    assert event["trace_id"] == "abc123fixed"


def test_make_log_event_generates_trace_id_when_omitted():
    from tools.log_generator.generator import make_log_event
    event = make_log_event("auth-service", "INFO", "test")
    assert len(event["trace_id"]) == 16


def test_make_log_event_accepts_metadata():
    from tools.log_generator.generator import make_log_event
    event = make_log_event("auth-service", "ERROR", "test", metadata={"pool_size": 10})
    assert event["metadata"]["pool_size"] == 10


def test_make_loki_payload_structure():
    from tools.log_generator.generator import make_log_event, make_loki_payload
    events = [make_log_event("auth-service", "ERROR", "test")]
    payload = make_loki_payload(events)
    assert "streams" in payload
    assert len(payload["streams"]) >= 1
    stream = payload["streams"][0]
    assert "stream" in stream
    assert "values" in stream
    assert stream["stream"]["service"] == "auth-service"
    assert stream["stream"]["severity"] == "ERROR"
    assert stream["stream"]["environment"] == "production"


def test_make_loki_payload_timestamp_is_nanoseconds():
    from tools.log_generator.generator import make_log_event, make_loki_payload
    events = [make_log_event("auth-service", "INFO", "test")]
    payload = make_loki_payload(events)
    ts_str = payload["streams"][0]["values"][0][0]
    ts_ns = int(ts_str)
    # Current time in ns is between 1e18 and 2e18
    assert 1_000_000_000_000_000_000 < ts_ns < 2_000_000_000_000_000_000


def test_make_loki_payload_value_is_json_string():
    from tools.log_generator.generator import make_log_event, make_loki_payload
    events = [make_log_event("auth-service", "INFO", "hello world")]
    payload = make_loki_payload(events)
    value_str = payload["streams"][0]["values"][0][1]
    parsed = json.loads(value_str)
    assert parsed["message"] == "hello world"


def test_make_loki_payload_groups_same_service_severity():
    from tools.log_generator.generator import make_log_event, make_loki_payload
    events = [
        make_log_event("auth-service", "ERROR", "msg1"),
        make_log_event("auth-service", "ERROR", "msg2"),
    ]
    payload = make_loki_payload(events)
    # Both events have same labels — should be one stream
    assert len(payload["streams"]) == 1
    assert len(payload["streams"][0]["values"]) == 2


def test_failure_cycle_returns_false_on_first_call(monkeypatch):
    monkeypatch.setattr(random, "uniform", lambda a, b: b)
    from tools.log_generator.generator import FailureCycle
    cycle = FailureCycle("test", interval_seconds=600, duration_seconds=60)
    # First call always initializes and returns False
    assert cycle.is_active() is False


def test_failure_cycle_active_during_burst(monkeypatch):
    base = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: base)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
    from tools.log_generator.generator import FailureCycle
    cycle = FailureCycle("test", interval_seconds=600, duration_seconds=60)
    cycle.is_active()  # initialize: _next_start = base + 0 = base
    monkeypatch.setattr(time, "monotonic", lambda: base + 1)
    assert cycle.is_active() is True


def test_failure_cycle_inactive_after_burst_ends(monkeypatch):
    base = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: base)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
    from tools.log_generator.generator import FailureCycle
    cycle = FailureCycle("test", interval_seconds=600, duration_seconds=60)
    cycle.is_active()  # initialize
    monkeypatch.setattr(time, "monotonic", lambda: base + 65)  # past 60s duration
    assert cycle.is_active() is False


def test_failure_cycle_inactive_before_next_interval(monkeypatch):
    base = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: base)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
    from tools.log_generator.generator import FailureCycle
    cycle = FailureCycle("test", interval_seconds=600, duration_seconds=60)
    cycle.is_active()  # initialize: _next_start = base
    monkeypatch.setattr(time, "monotonic", lambda: base + 65)  # past burst
    cycle.is_active()  # advance _next_start to base + 600
    monkeypatch.setattr(time, "monotonic", lambda: base + 300)  # mid-interval
    assert cycle.is_active() is False
