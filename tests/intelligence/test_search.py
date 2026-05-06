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
