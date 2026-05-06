# tests/intelligence/test_analyze.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel
from models.rca import RootCauseAnalysis


def _make_event(**kwargs) -> LogEvent:
    defaults = dict(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="connection refused to db:5432",
        source="loki",
        trace_id="trace-abc",
    )
    return LogEvent(**{**defaults, **kwargs})


_RCA_CONFIG = {
    "semantic_neighbors": True,
    "max_semantic_k": 5,
    "trace_logs": True,
    "max_trace_logs": 20,
    "model": "claude-sonnet-4-20250514",
    "timeout_seconds": 30,
}

_CLAUDE_RESPONSE_JSON = json.dumps({
    "summary": "Auth service DB connection failure",
    "root_cause": "Connection pool exhausted under load",
    "affected_services": ["auth-service"],
    "confidence": 0.9,
    "suggested_fixes": ["Increase pool size", "Add circuit breaker"],
})


@pytest.mark.asyncio
async def test_build_rca_context_fetches_target_log():
    from intelligence.analyze import build_rca_context, RCAContext
    event = _make_event()

    with patch("intelligence.analyze.fetch_logs_by_ids") as mock_fetch, \
         patch("intelligence.analyze.embed_texts", return_value=[[0.1] * 1536]), \
         patch("intelligence.analyze.search_vectors", return_value=[("log-002", 0.85)]):
        mock_fetch.side_effect = [[event], [_make_event(id="log-002")]]

        ctx = await build_rca_context(
            log_id="log-001",
            pool=MagicMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            config=_RCA_CONFIG,
            collection="log_events",
        )

    assert ctx.target.id == "log-001"


@pytest.mark.asyncio
async def test_build_rca_context_raises_value_error_when_log_not_found():
    from intelligence.analyze import build_rca_context

    with patch("intelligence.analyze.fetch_logs_by_ids", return_value=[]):
        with pytest.raises(ValueError, match="log-999"):
            await build_rca_context(
                log_id="log-999",
                pool=MagicMock(),
                openai_client=AsyncMock(),
                qdrant_client=AsyncMock(),
                config=_RCA_CONFIG,
                collection="log_events",
            )


@pytest.mark.asyncio
async def test_build_rca_context_skips_semantic_when_disabled():
    from intelligence.analyze import build_rca_context
    event = _make_event()
    config = {**_RCA_CONFIG, "semantic_neighbors": False, "trace_logs": False}

    with patch("intelligence.analyze.fetch_logs_by_ids", return_value=[event]), \
         patch("intelligence.analyze.embed_texts") as mock_embed:

        ctx = await build_rca_context(
            log_id="log-001",
            pool=MagicMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            config=config,
            collection="log_events",
        )

    mock_embed.assert_not_called()
    assert ctx.semantic_neighbors == []
    assert ctx.trace_logs == []


@pytest.mark.asyncio
async def test_run_rca_parses_claude_response():
    from intelligence.analyze import run_rca, RCAContext
    event = _make_event()
    ctx = RCAContext(target=event)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_CLAUDE_RESPONSE_JSON)]
    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(return_value=mock_message)

    rca = await run_rca(ctx, mock_anthropic, _RCA_CONFIG)

    assert rca.log_id == "log-001"
    assert rca.confidence == 0.9
    assert len(rca.suggested_fixes) == 2


@pytest.mark.asyncio
async def test_run_rca_raises_runtime_error_on_timeout():
    import asyncio
    from intelligence.analyze import run_rca, RCAContext
    ctx = RCAContext(target=_make_event())
    mock_anthropic = AsyncMock()
    mock_anthropic.messages.create = AsyncMock(side_effect=asyncio.TimeoutError)

    with pytest.raises(RuntimeError, match="timed out"):
        await run_rca(ctx, mock_anthropic, _RCA_CONFIG)


@pytest.mark.asyncio
async def test_create_tasks_from_rca_derives_priority_from_confidence():
    from intelligence.analyze import create_tasks_from_rca
    rca = RootCauseAnalysis(
        log_id="log-001",
        summary="s",
        root_cause="r",
        confidence=0.9,
        suggested_fixes=["Fix A", "Fix B"],
    )

    with patch("intelligence.analyze.insert_task", return_value=None):
        tasks = await create_tasks_from_rca(rca, MagicMock())

    assert len(tasks) == 2
    assert all(t.priority.value == "high" for t in tasks)


@pytest.mark.asyncio
async def test_create_tasks_from_rca_medium_priority_for_mid_confidence():
    from intelligence.analyze import create_tasks_from_rca
    rca = RootCauseAnalysis(
        log_id="log-001",
        summary="s",
        root_cause="r",
        confidence=0.6,
        suggested_fixes=["Fix A"],
    )

    with patch("intelligence.analyze.insert_task", return_value=None):
        tasks = await create_tasks_from_rca(rca, MagicMock())

    assert tasks[0].priority.value == "medium"
