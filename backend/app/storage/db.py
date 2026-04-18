from __future__ import annotations

import logging

import asyncpg

from app.config import get_settings

log = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def ensure_schema() -> None:
    """Run the initial migration if the table doesn't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT to_regclass('public.analysis_reports')"
        )
        if exists is None:
            log.info("Creating schema (first run)")
            from pathlib import Path

            sql_path = (
                Path(__file__).resolve().parent.parent.parent / "migrations" / "001_initial.sql"
            )
            sql = sql_path.read_text()
            await conn.execute(sql)
