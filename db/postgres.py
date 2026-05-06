from __future__ import annotations

from pathlib import Path

import asyncpg

_MIGRATION_SQL = (Path(__file__).parent / "migrations" / "001_init.sql").read_text()


async def init_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        await conn.execute(_MIGRATION_SQL)
    return pool
