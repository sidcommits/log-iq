from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel


def _make_event(**kwargs) -> LogEvent:
    defaults = dict(
        id="test-id-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth-service",
        environment="production",
        message="connection pool exhausted",
        source="loki",
    )
    return LogEvent(**{**defaults, **kwargs})


def test_chunk_message_returns_single_chunk_for_short_text():
    from ingestion.pipeline import chunk_message
    result = chunk_message("short message")
    assert result == ["short message"]


def test_chunk_message_splits_text_exceeding_512_tokens():
    from ingestion.pipeline import chunk_message
    # 600 repetitions of "word " is well above 512 tokens
    long_text = " ".join(["word"] * 600)
    result = chunk_message(long_text)
    assert len(result) > 1


@pytest.mark.asyncio
async def test_process_batch_embeds_and_upserts_then_marks():
    from ingestion.pipeline import IngestionWorker

    pool = MagicMock()
    openai_client = AsyncMock()
    qdrant_client = AsyncMock()
    event = _make_event()

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]) as mock_fetch, \
         patch("ingestion.pipeline.mark_embedded") as mock_mark, \
         patch("ingestion.pipeline.upsert_vectors") as mock_upsert, \
         patch("ingestion.pipeline.embed_texts", return_value=[[0.1] * 1536]):

        worker = IngestionWorker(pool, openai_client, qdrant_client)
        result = await worker._process_batch()

    assert result is True
    mock_fetch.assert_called_once_with(pool, 100)
    mock_upsert.assert_called_once()
    ids_arg = mock_mark.call_args[0][1]
    assert "test-id-001" in ids_arg


@pytest.mark.asyncio
async def test_process_batch_returns_false_when_no_events():
    from ingestion.pipeline import IngestionWorker

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[]):
        worker = IngestionWorker(MagicMock(), AsyncMock(), AsyncMock())
        result = await worker._process_batch()

    assert result is False


@pytest.mark.asyncio
async def test_process_batch_does_not_mark_embedded_on_openai_failure():
    from ingestion.pipeline import IngestionWorker

    event = _make_event()

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]), \
         patch("ingestion.pipeline.embed_texts", side_effect=Exception("OpenAI down")), \
         patch("ingestion.pipeline.mark_embedded") as mock_mark:

        worker = IngestionWorker(MagicMock(), AsyncMock(), AsyncMock())
        with pytest.raises(Exception, match="OpenAI down"):
            await worker._process_batch()

    mock_mark.assert_not_called()


@pytest.mark.asyncio
async def test_worker_start_stop_lifecycle():
    from ingestion.pipeline import IngestionWorker
    import asyncio

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[]):
        worker = IngestionWorker(MagicMock(), AsyncMock(), AsyncMock(), poll_interval=0.01)
        await worker.start()
        assert worker._task is not None
        await asyncio.sleep(0.05)
        await worker.stop()
        assert worker._task.done()


@pytest.mark.asyncio
async def test_process_batch_calls_score_batch_after_upsert():
    from ingestion.pipeline import IngestionWorker
    from models.anomaly import AnomalyResult
    from datetime import datetime, timezone

    event = LogEvent(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth",
        environment="prod",
        message="err",
        source="loki",
    )
    anomaly = AnomalyResult(log_id="log-001", score=0.4, is_anomaly=True, threshold=0.72)

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]), \
         patch("ingestion.pipeline.embed_texts", return_value=[[0.1] * 1536]), \
         patch("ingestion.pipeline.upsert_vectors"), \
         patch("ingestion.pipeline.mark_embedded"), \
         patch("ingestion.pipeline.score_batch", return_value=[anomaly]) as mock_score, \
         patch("ingestion.pipeline.insert_anomaly") as mock_insert:

        worker = IngestionWorker(
            pool=AsyncMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            anomaly_config={"knn_k": 10, "threshold": 0.72},
        )
        await worker._process_batch()

    mock_score.assert_called_once()
    mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_process_batch_continues_when_score_batch_raises():
    from ingestion.pipeline import IngestionWorker
    from datetime import datetime, timezone

    event = LogEvent(
        id="log-001",
        timestamp=datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc),
        severity=SeverityLevel.ERROR,
        service="auth",
        environment="prod",
        message="err",
        source="loki",
    )

    with patch("ingestion.pipeline.fetch_unembedded_logs", return_value=[event]), \
         patch("ingestion.pipeline.embed_texts", return_value=[[0.1] * 1536]), \
         patch("ingestion.pipeline.upsert_vectors"), \
         patch("ingestion.pipeline.score_batch", side_effect=Exception("qdrant down")), \
         patch("ingestion.pipeline.mark_embedded") as mock_mark:

        worker = IngestionWorker(
            pool=AsyncMock(),
            openai_client=AsyncMock(),
            qdrant_client=AsyncMock(),
            anomaly_config={"knn_k": 10, "threshold": 0.72},
        )
        result = await worker._process_batch()

    assert result is True
    mock_mark.assert_called_once()
