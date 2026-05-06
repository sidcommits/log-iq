from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.postgres import get_cursor, init_pool, upsert_cursor
from db.postgres import fetch_logs_by_ids, fetch_logs_by_text, fetch_unembedded_logs, mark_embedded
from models.log_event import LogEvent, SeverityLevel


def _make_mock_pool():
    """Return (pool_mock, conn_mock) with acquire() wired as async context manager."""
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool, conn


@pytest.mark.asyncio
async def test_init_pool_creates_pool_and_runs_migration(monkeypatch):
    mock_pool, mock_conn = _make_mock_pool()

    async def fake_create_pool(dsn):
        return mock_pool

    monkeypatch.setattr("asyncpg.create_pool", fake_create_pool)

    result = await init_pool("postgresql://test/db")

    assert result is mock_pool
    mock_conn.execute.assert_called_once()
    sql_arg = mock_conn.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS sync_cursors" in sql_arg
    assert "CREATE TABLE IF NOT EXISTS logs" in sql_arg


@pytest.mark.asyncio
async def test_get_cursor_returns_none_when_no_row():
    mock_pool, mock_conn = _make_mock_pool()
    mock_conn.fetchrow.return_value = None

    result = await get_cursor(mock_pool, "loki")

    assert result is None
    mock_conn.fetchrow.assert_called_once_with(
        "SELECT last_synced_at FROM sync_cursors WHERE source_name = $1",
        "loki",
    )


@pytest.mark.asyncio
async def test_get_cursor_returns_datetime_when_row_exists():
    mock_pool, mock_conn = _make_mock_pool()
    ts = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)
    mock_conn.fetchrow.return_value = {"last_synced_at": ts}

    result = await get_cursor(mock_pool, "loki")

    assert result == ts


@pytest.mark.asyncio
async def test_upsert_cursor_executes_insert_on_conflict():
    mock_pool, mock_conn = _make_mock_pool()
    ts = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

    await upsert_cursor(mock_pool, "loki", ts)

    mock_conn.execute.assert_called_once()
    sql, source_arg, ts_arg = mock_conn.execute.call_args[0]
    assert "INSERT INTO sync_cursors" in sql
    assert "ON CONFLICT" in sql
    assert source_arg == "loki"
    assert ts_arg == ts


from db.postgres import insert_logs


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


@pytest.mark.asyncio
async def test_insert_logs_calls_executemany_with_correct_columns():
    mock_pool, mock_conn = _make_mock_pool()
    event = _make_event()

    count = await insert_logs(mock_pool, [event])

    mock_conn.executemany.assert_called_once()
    sql, records = mock_conn.executemany.call_args[0]
    assert "INSERT INTO logs" in sql
    assert "ON CONFLICT (id) DO NOTHING" in sql
    assert len(records) == 1
    row = records[0]
    assert row[0] == "test-id-001"
    assert row[2] == "ERROR"
    assert row[3] == "auth-service"
    assert count == 1


@pytest.mark.asyncio
async def test_insert_logs_returns_zero_for_empty_list():
    mock_pool, mock_conn = _make_mock_pool()

    count = await insert_logs(mock_pool, [])

    mock_conn.executemany.assert_not_called()
    assert count == 0


@pytest.mark.asyncio
async def test_insert_logs_passes_all_events_as_records():
    mock_pool, mock_conn = _make_mock_pool()
    events = [_make_event(id=f"id-{i}", message=f"msg-{i}") for i in range(3)]

    count = await insert_logs(mock_pool, events)

    _, records = mock_conn.executemany.call_args[0]
    assert len(records) == 3
    assert count == 3


@pytest.mark.asyncio
async def test_fetch_unembedded_logs_queries_where_embedded_at_is_null():
    mock_pool, mock_conn = _make_mock_pool()
    mock_conn.fetch.return_value = []

    result = await fetch_unembedded_logs(mock_pool, limit=50)

    mock_conn.fetch.assert_called_once()
    sql, limit_arg = mock_conn.fetch.call_args[0]
    assert "embedded_at IS NULL" in sql
    assert limit_arg == 50
    assert result == []


@pytest.mark.asyncio
async def test_mark_embedded_executes_update():
    mock_pool, mock_conn = _make_mock_pool()

    await mark_embedded(mock_pool, ["id-1", "id-2"])

    mock_conn.execute.assert_called_once()
    sql, ids_arg = mock_conn.execute.call_args[0]
    assert "UPDATE logs SET embedded_at" in sql
    assert ids_arg == ["id-1", "id-2"]


@pytest.mark.asyncio
async def test_mark_embedded_skips_empty_list():
    mock_pool, mock_conn = _make_mock_pool()

    await mark_embedded(mock_pool, [])

    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_logs_by_ids_returns_empty_without_query():
    mock_pool, mock_conn = _make_mock_pool()

    result = await fetch_logs_by_ids(mock_pool, [])

    mock_conn.fetch.assert_not_called()
    assert result == []


@pytest.mark.asyncio
async def test_fetch_logs_by_text_queries_ilike():
    mock_pool, mock_conn = _make_mock_pool()
    mock_conn.fetch.return_value = []

    result = await fetch_logs_by_text(mock_pool, "auth error", limit=10)

    mock_conn.fetch.assert_called_once()
    sql, query_arg, limit_arg = mock_conn.fetch.call_args[0]
    assert "ILIKE" in sql
    assert "%auth error%" in query_arg
    assert limit_arg == 10
    assert result == []


@pytest.mark.asyncio
async def test_fetch_unembedded_logs_deserialises_row_to_log_event():
    mock_pool, mock_conn = _make_mock_pool()
    ts = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)
    # asyncpg returns a dict-like Record; use a plain dict in tests
    mock_row = {
        "id": "log-abc",
        "timestamp": ts,
        "severity": "ERROR",
        "service": "auth-service",
        "environment": "production",
        "trace_id": None,
        "span_id": None,
        "message": "connection refused",
        "metadata": {},
        "raw": {},
        "source": "loki",
    }
    mock_conn.fetch.return_value = [mock_row]

    result = await fetch_unembedded_logs(mock_pool, limit=1)

    assert len(result) == 1
    event = result[0]
    assert event.id == "log-abc"
    assert event.severity.value == "ERROR"
    assert event.service == "auth-service"
    assert event.timestamp == ts
