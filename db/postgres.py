from __future__ import annotations

from datetime import datetime
from pathlib import Path

import asyncpg

from models.log_event import LogEvent, SeverityLevel

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_SQL = "\n".join(
    p.read_text()
    for p in sorted(_MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
)


def _row_to_log_event(row) -> LogEvent:
    return LogEvent(
        id=row["id"],
        timestamp=row["timestamp"],
        severity=SeverityLevel(row["severity"]),
        service=row["service"],
        environment=row["environment"],
        trace_id=row["trace_id"],
        span_id=row["span_id"],
        message=row["message"],
        metadata=row["metadata"] or {},
        raw=row["raw"] or {},
        source=row["source"],
    )


async def init_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        await conn.execute(_MIGRATION_SQL)
    return pool


async def get_cursor(pool: asyncpg.Pool, source_name: str) -> datetime | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_synced_at FROM sync_cursors WHERE source_name = $1",
            source_name,
        )
    return row["last_synced_at"] if row else None


async def upsert_cursor(pool: asyncpg.Pool, source_name: str, ts: datetime) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sync_cursors (source_name, last_synced_at, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (source_name)
            DO UPDATE SET last_synced_at = EXCLUDED.last_synced_at,
                          updated_at = NOW()
            """,
            source_name,
            ts,
        )


async def insert_logs(pool: asyncpg.Pool, events: list[LogEvent]) -> int:
    if not events:
        return 0
    records = [
        (
            e.id,
            e.timestamp,
            e.severity.value,
            e.service,
            e.environment,
            e.trace_id,
            e.span_id,
            e.message,
            dict(e.metadata),
            dict(e.raw),
            e.source,
        )
        for e in events
    ]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO logs
                (id, timestamp, severity, service, environment,
                 trace_id, span_id, message, metadata, raw, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (id) DO NOTHING
            """,
            records,
        )
    return len(events)


async def fetch_unembedded_logs(pool: asyncpg.Pool, limit: int = 100) -> list[LogEvent]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM logs WHERE embedded_at IS NULL ORDER BY timestamp ASC LIMIT $1",
            limit,
        )
    return [_row_to_log_event(row) for row in rows]


async def mark_embedded(pool: asyncpg.Pool, ids: list[str]) -> None:
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE logs SET embedded_at = NOW() WHERE id = ANY($1)",
            ids,
        )


async def fetch_logs_by_ids(pool: asyncpg.Pool, ids: list[str]) -> list[LogEvent]:
    if not ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM logs WHERE id = ANY($1)",
            ids,
        )
    return [_row_to_log_event(row) for row in rows]


async def fetch_logs_by_text(pool: asyncpg.Pool, query: str, limit: int) -> list[LogEvent]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM logs WHERE message ILIKE $1 ORDER BY timestamp DESC LIMIT $2",
            f"%{query}%",
            limit,
        )
    return [_row_to_log_event(row) for row in rows]
