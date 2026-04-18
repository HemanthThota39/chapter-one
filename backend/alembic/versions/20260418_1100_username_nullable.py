"""username nullable until onboarding

Revision ID: 0002_username_nullable
Revises: 0001_init_users
Create Date: 2026-04-18 11:00:00 UTC

On first sign-in we INSERT a user record with username=NULL and populate
it later during onboarding. The original migration made username NOT NULL
which blocked first-sign-in. Postgres UNIQUE allows multiple NULLs, which
is exactly what we want for a "not yet onboarded" state.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_username_nullable"
down_revision: Union[str, None] = "0001_init_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN username DROP NOT NULL;")


def downgrade() -> None:
    op.execute("UPDATE users SET username = id::text WHERE username IS NULL;")
    op.execute("ALTER TABLE users ALTER COLUMN username SET NOT NULL;")
