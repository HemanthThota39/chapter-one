"""Alembic environment — async + SQLAlchemy 2 style.

Connection string from DATABASE_URL env var (same secret as the API uses).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)


def _db_url() -> str:
    """Normalise DATABASE_URL to SQLAlchemy+asyncpg form and strip libpq-only params."""
    from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError("DATABASE_URL env var is required")
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)

    # asyncpg does NOT accept libpq-style `sslmode`; strip it (we pass ssl=True via connect_args)
    parts = urlsplit(raw)
    params = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k != "sslmode"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


config.set_main_option("sqlalchemy.url", _db_url())

target_metadata = None  # we author raw SQL migrations; no autogenerate


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"ssl": True},  # Flexible Server requires SSL
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
