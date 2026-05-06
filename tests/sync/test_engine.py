import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.log_event import LogEvent, SeverityLevel
from sync.engine import SourceWorker


def _make_event(n: int = 0) -> LogEvent:
    return LogEvent(
        id=f"evt-{n}",
        timestamp=datetime(2026, 5, 6, 10, 0, n, tzinfo=timezone.utc),
        severity=SeverityLevel.INFO,
        service="svc",
        environment="production",
        message=f"msg-{n}",
        source="loki",
    )


def _make_adapter(events: list[LogEvent] | None = None) -> MagicMock:
    adapter = MagicMock()
    adapter.get_source_name.return_value = "loki"
    adapter.fetch_logs = AsyncMock(return_value=events or [])
    return adapter


def _make_pool() -> MagicMock:
    return MagicMock()


# ── _poll_once ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_once_fetches_with_cursor_when_cursor_exists():
    ts = datetime(2026, 5, 6, 9, 0, 0, tzinfo=timezone.utc)
    adapter = _make_adapter([_make_event()])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=ts)), \
         patch("sync.engine.db.insert_logs", AsyncMock()) as mock_insert, \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        await worker._poll_once()

    adapter.fetch_logs.assert_called_once()
    call_kwargs = adapter.fetch_logs.call_args
    assert call_kwargs.kwargs["start"] == ts
    mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_poll_once_defaults_start_when_no_cursor():
    adapter = _make_adapter([])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll", poll_interval=30)
        before = datetime.now(tz=timezone.utc)
        await worker._poll_once()
        after = datetime.now(tz=timezone.utc)

    start_arg = adapter.fetch_logs.call_args.kwargs["start"]
    expected_start = before - timedelta(seconds=30)
    assert abs((start_arg - expected_start).total_seconds()) < 1.0


@pytest.mark.asyncio
async def test_poll_once_skips_insert_when_no_events():
    adapter = _make_adapter([])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()) as mock_insert, \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        await worker._poll_once()

    mock_insert.assert_not_called()


@pytest.mark.asyncio
async def test_poll_once_always_upserts_cursor():
    adapter = _make_adapter([])
    pool = _make_pool()

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()) as mock_upsert:
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        await worker._poll_once()

    mock_upsert.assert_called_once()
    source_arg = mock_upsert.call_args[0][1]
    assert source_arg == "loki"


# ── backoff ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backoff_doubles_on_consecutive_failures():
    adapter = _make_adapter()
    adapter.fetch_logs.side_effect = RuntimeError("loki down")
    pool = _make_pool()

    sleep_calls = []

    async def fake_sleep(n):
        sleep_calls.append(n)
        if len(sleep_calls) >= 3:
            raise asyncio.CancelledError

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll")
        with pytest.raises(asyncio.CancelledError):
            await worker._poll_loop()

    assert sleep_calls[0] == 1.0
    assert sleep_calls[1] == 2.0


@pytest.mark.asyncio
async def test_backoff_resets_on_success():
    adapter = _make_adapter([])
    pool = _make_pool()
    call_count = 0

    async def flaky_fetch(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient error")
        if call_count == 3:
            raise asyncio.CancelledError
        return []

    adapter.fetch_logs.side_effect = flaky_fetch

    sleep_calls = []

    async def fake_sleep(n):
        sleep_calls.append(n)

    with patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()), \
         patch("asyncio.sleep", side_effect=fake_sleep):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="poll", poll_interval=30)
        with pytest.raises(asyncio.CancelledError):
            await worker._poll_loop()

    # First sleep is backoff (1.0), second sleep is normal poll interval (30)
    assert sleep_calls[0] == 1.0
    assert sleep_calls[1] == 30


# ── stream mode ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_worker_flushes_at_batch_size():
    pool = _make_pool()
    events = [_make_event(i) for i in range(5)]
    captured_batches: list[list] = []

    async def fake_stream():
        for e in events:
            yield e

    async def capturing_insert(p, evts):
        captured_batches.append(list(evts))  # snapshot before buffer.clear()

    adapter = _make_adapter()
    adapter.stream_logs.return_value = fake_stream()

    with patch("sync.engine.db.insert_logs", side_effect=capturing_insert):
        worker = SourceWorker(
            adapter=adapter,
            pool=pool,
            mode="stream",
            stream_batch_size=3,
            stream_flush_interval=5.0,
        )
        await worker._stream_once()

    # 5 events with batch_size=3: first flush at 3 events, second flush with 2
    assert len(captured_batches) == 2
    assert len(captured_batches[0]) == 3
    assert len(captured_batches[1]) == 2


@pytest.mark.asyncio
async def test_stream_worker_flushes_on_timeout():
    pool = _make_pool()
    event = _make_event()
    flushed = asyncio.Event()

    async def mock_insert(p, evts):
        flushed.set()

    async def trickle():
        yield event
        await asyncio.sleep(10)  # longer than flush_interval — triggers timeout

    adapter = _make_adapter()
    adapter.stream_logs.return_value = trickle()

    with patch("sync.engine.db.insert_logs", side_effect=mock_insert):
        worker = SourceWorker(
            adapter=adapter,
            pool=pool,
            mode="stream",
            stream_batch_size=100,
            stream_flush_interval=0.05,
        )
        task = asyncio.create_task(worker._stream_once())
        await asyncio.wait_for(flushed.wait(), timeout=2.0)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    assert flushed.is_set()


@pytest.mark.asyncio
async def test_stream_worker_start_creates_stream_task():
    pool = _make_pool()
    adapter = _make_adapter()

    async def infinite_stream():
        while True:
            await asyncio.sleep(1)
            yield _make_event()

    adapter.stream_logs.return_value = infinite_stream()

    with patch("sync.engine.db.insert_logs", AsyncMock()), \
         patch("sync.engine.db.get_cursor", AsyncMock(return_value=None)), \
         patch("sync.engine.db.upsert_cursor", AsyncMock()):
        worker = SourceWorker(adapter=adapter, pool=pool, mode="stream")
        await worker.start()
        assert worker._task is not None
        assert not worker._task.done()
        await worker.stop()
        assert worker._task.cancelled() or worker._task.done()
