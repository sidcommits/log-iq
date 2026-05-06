from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel
from models.rca import RootCauseAnalysis


def _make_event(id="log-001", service="auth-service", **kwargs) -> LogEvent:
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
