from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.postgres import init_pool


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
