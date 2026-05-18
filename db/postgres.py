from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import asyncpg

from models.anomaly import AnomalyResult
from models.log_event import LogEvent, SeverityLevel
from models.rca import RootCauseAnalysis
from models.task import ActionableTask, TaskPriority, TaskStatus

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


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def init_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn, init=_init_conn)
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


# ---------------------------------------------------------------------------
# RCA helpers
# ---------------------------------------------------------------------------

def _row_to_rca(row) -> RootCauseAnalysis:
    return RootCauseAnalysis(
        id=row["id"],
        log_id=row["log_id"],
        trace_id=row["trace_id"],
        summary=row["summary"],
        root_cause=row["root_cause"],
        affected_services=list(row["affected_services"] or []),
        confidence=row["confidence"],
        suggested_fixes=list(row["suggested_fixes"] or []),
        created_at=row["created_at"],
    )


async def insert_rca(pool: asyncpg.Pool, rca: RootCauseAnalysis) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO rca
                (id, log_id, trace_id, summary, root_cause,
                 affected_services, confidence, suggested_fixes, created_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8::jsonb, $9)
            """,
            rca.id, rca.log_id, rca.trace_id, rca.summary, rca.root_cause,
            json.dumps(rca.affected_services), rca.confidence,
            json.dumps(rca.suggested_fixes), rca.created_at,
        )


async def get_rca_by_log_ids(pool: asyncpg.Pool, log_ids: list[str]) -> list[RootCauseAnalysis]:
    if not log_ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM rca WHERE log_id = ANY($1)", log_ids)
    return [_row_to_rca(row) for row in rows]


async def get_logs_by_trace_id(pool: asyncpg.Pool, trace_id: str, limit: int = 200) -> list[LogEvent]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM logs WHERE trace_id = $1 ORDER BY timestamp ASC LIMIT $2",
            trace_id, limit,
        )
    return [_row_to_log_event(row) for row in rows]


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------

async def append_audit_log(pool: asyncpg.Pool, event_type: str, payload: dict) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO audit_log (event_type, payload) VALUES ($1, $2::jsonb)",
            event_type, json.dumps(payload),
        )


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------

def _row_to_task(row) -> ActionableTask:
    return ActionableTask(
        id=row["id"],
        rca_id=row["rca_id"],
        log_id=row["log_id"],
        title=row["title"],
        description=row["description"],
        status=TaskStatus(row["status"]),
        priority=TaskPriority(row["priority"]),
        agent_id=row["agent_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def insert_task(pool: asyncpg.Pool, task: ActionableTask) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tasks
                (id, rca_id, log_id, title, description, status, priority, agent_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            task.id, task.rca_id, task.log_id, task.title, task.description,
            task.status.value, task.priority.value, task.agent_id,
            task.created_at, task.updated_at,
        )


async def get_tasks(
    pool: asyncpg.Pool,
    status: str | None,
    priority: str | None,
    limit: int,
    offset: int,
) -> tuple[list[ActionableTask], int]:
    conditions: list[str] = []
    params: list = []
    if status is not None:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    if priority is not None:
        params.append(priority)
        conditions.append(f"priority = ${len(params)}")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    count_params = params[:]
    params += [limit, offset]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}",
            *params,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tasks {where}", *count_params)
    return [_row_to_task(row) for row in rows], (total or 0)


async def get_task_by_id(pool: asyncpg.Pool, task_id: str) -> ActionableTask | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    return _row_to_task(row) if row else None


async def update_task_status(
    pool: asyncpg.Pool, task_id: str, new_status: str
) -> ActionableTask | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE tasks SET status = $1, updated_at = NOW() WHERE id = $2 RETURNING *",
            new_status, task_id,
        )
    return _row_to_task(row) if row else None


# ---------------------------------------------------------------------------
# Anomaly helpers
# ---------------------------------------------------------------------------

def _row_to_anomaly(row) -> AnomalyResult:
    log = None
    if row.get("l_service") is not None:
        log = LogEvent(
            id=row["l_id"],
            timestamp=row["l_timestamp"],
            severity=SeverityLevel(row["l_severity"]),
            service=row["l_service"],
            environment=row["l_environment"],
            trace_id=row["l_trace_id"],
            span_id=row["l_span_id"],
            message=row["l_message"],
            metadata=row["l_metadata"] or {},
            raw=row["l_raw"] or {},
            source=row["l_source"],
        )
    return AnomalyResult(
        id=row["id"],
        log_id=row["log_id"],
        score=row["score"],
        is_anomaly=row["is_anomaly"],
        threshold=row["threshold"],
        reviewed=row["reviewed"],
        detected_at=row["detected_at"],
        log=log,
    )


async def insert_anomaly(pool: asyncpg.Pool, anomaly: AnomalyResult) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO anomalies (id, log_id, score, is_anomaly, threshold, reviewed, detected_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO NOTHING
            """,
            anomaly.id, anomaly.log_id, anomaly.score, anomaly.is_anomaly,
            anomaly.threshold, anomaly.reviewed, anomaly.detected_at,
        )


async def get_anomalies(
    pool: asyncpg.Pool,
    reviewed: bool | None,
    is_anomaly: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[AnomalyResult], int]:
    conditions: list[str] = []
    params: list = []
    if reviewed is not None:
        params.append(reviewed)
        conditions.append(f"reviewed = ${len(params)}")
    if is_anomaly is not None:
        params.append(is_anomaly)
        conditions.append(f"is_anomaly = ${len(params)}")
    where = ("WHERE " + " AND ".join(f"a.{c}" for c in conditions)) if conditions else ""
    count_params = params[:]
    params += [limit, offset]
    join_query = f"""
        SELECT
            a.id, a.log_id, a.score, a.is_anomaly, a.threshold, a.reviewed, a.detected_at,
            l.id        AS l_id,
            l.timestamp AS l_timestamp,
            l.severity  AS l_severity,
            l.service   AS l_service,
            l.environment AS l_environment,
            l.trace_id  AS l_trace_id,
            l.span_id   AS l_span_id,
            l.message   AS l_message,
            l.metadata  AS l_metadata,
            l.raw       AS l_raw,
            l.source    AS l_source
        FROM anomalies a
        LEFT JOIN logs l ON l.id = a.log_id
        {where}
        ORDER BY a.detected_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(join_query, *params)
        total = await conn.fetchval(f"SELECT COUNT(*) FROM anomalies a {where}", *count_params)
    return [_row_to_anomaly(row) for row in rows], (total or 0)


async def mark_anomaly_reviewed(pool: asyncpg.Pool, anomaly_id: str) -> AnomalyResult | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE anomalies SET reviewed = TRUE WHERE id = $1 RETURNING *",
            anomaly_id,
        )
    return _row_to_anomaly(row) if row else None
