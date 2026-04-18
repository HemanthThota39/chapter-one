"""initial: users table + extensions

Revision ID: 0001_init_users
Revises:
Create Date: 2026-04-18 09:00:00 UTC
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_init_users"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions required by the schema
    op.execute("CREATE EXTENSION IF NOT EXISTS citext;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.execute("""
        CREATE TABLE users (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            external_id         TEXT NOT NULL UNIQUE,
            email               TEXT NOT NULL UNIQUE,
            username            CITEXT NOT NULL UNIQUE,
            display_name        TEXT NOT NULL,
            avatar_kind         TEXT NOT NULL CHECK (avatar_kind IN ('upload','library','initials')),
            avatar_url          TEXT,
            avatar_seed         TEXT,
            timezone            TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            default_visibility  TEXT NOT NULL DEFAULT 'public' CHECK (default_visibility IN ('public','private')),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            total_analyses      INTEGER NOT NULL DEFAULT 0,
            current_streak      INTEGER NOT NULL DEFAULT 0,
            longest_streak      INTEGER NOT NULL DEFAULT 0,
            fires_received      INTEGER NOT NULL DEFAULT 0,
            last_activity_date  DATE
        );
    """)

    op.execute("CREATE INDEX idx_users_username_trgm ON users USING GIN (username gin_trgm_ops);")
    op.execute("CREATE INDEX idx_users_created_at     ON users (created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users;")
    # Extensions intentionally NOT dropped on downgrade — other features depend on them
