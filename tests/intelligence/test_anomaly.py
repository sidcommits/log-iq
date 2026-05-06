from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel


def _make_event(id: str = "log-001", **kwargs) -> LogEvent:
    return LogEvent(
        id=id,
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="db connection refused",
        source="loki",
        **kwargs,
    )


_ANOMALY_CONFIG = {"knn_k": 10, "threshold": 0.72}


@pytest.mark.asyncio
async def test_score_batch_flags_anomaly_when_avg_similarity_below_threshold():
    from intelligence.anomaly import score_batch
    event = _make_event()
    # avg similarity = 0.5 → is_anomaly=True (below 0.72 threshold)
    neighbors = [("log-002", 0.5), ("log-003", 0.5)]

    with patch("intelligence.anomaly.search_vectors", return_value=neighbors):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    assert len(results) == 1
    assert results[0].is_anomaly is True
    assert results[0].log_id == "log-001"
    assert results[0].score == pytest.approx(0.5)  # 1.0 - 0.5


@pytest.mark.asyncio
async def test_score_batch_no_anomaly_when_avg_similarity_above_threshold():
    from intelligence.anomaly import score_batch
    event = _make_event()
    neighbors = [("log-002", 0.9), ("log-003", 0.85)]

    with patch("intelligence.anomaly.search_vectors", return_value=neighbors):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    assert results[0].is_anomaly is False


@pytest.mark.asyncio
async def test_score_batch_excludes_self_from_neighbors():
    from intelligence.anomaly import score_batch
    event = _make_event(id="log-001")
    # "log-001" is self — should be excluded; only log-002 remains
    hits = [("log-001", 1.0), ("log-002", 0.5)]

    with patch("intelligence.anomaly.search_vectors", return_value=hits):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    # avg_sim = 0.5 (self excluded), score = 0.5
    assert results[0].score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_score_batch_returns_empty_for_empty_input():
    from intelligence.anomaly import score_batch
    results = await score_batch(
        events=[],
        query_vectors=[],
        qdrant_client=AsyncMock(),
        config=_ANOMALY_CONFIG,
        collection="log_events",
    )
    assert results == []


@pytest.mark.asyncio
async def test_score_batch_treats_no_neighbors_as_anomaly():
    from intelligence.anomaly import score_batch
    event = _make_event()

    with patch("intelligence.anomaly.search_vectors", return_value=[]):
        results = await score_batch(
            events=[event],
            query_vectors=[[0.1] * 1536],
            qdrant_client=AsyncMock(),
            config=_ANOMALY_CONFIG,
            collection="log_events",
        )

    assert results[0].is_anomaly is True
    assert results[0].score == pytest.approx(1.0)
