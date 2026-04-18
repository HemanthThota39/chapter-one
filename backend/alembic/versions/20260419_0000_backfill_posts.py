"""Backfill posts for public+done analyses that missed auto-post creation

Revision ID: 0005_backfill_posts
Revises: 0004_social
Create Date: 2026-04-19 00:00:00 UTC

0004_social landed the tables, but any analysis that finished *before*
the migration applied on a given environment never got its row in
`posts` — the worker's create_post_if_missing hit an UndefinedTableError
and caught it silently. Result: the global feed was empty even when
public completed analyses existed.

This is a one-shot forward fix. ON CONFLICT DO NOTHING keeps it
idempotent, and there's no destructive downgrade.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_backfill_posts"
down_revision: Union[str, None] = "0004_social"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO posts (analysis_id, owner_id)
        SELECT id, owner_id
          FROM analyses
         WHERE visibility = 'public' AND status = 'done'
        ON CONFLICT (analysis_id) DO NOTHING;
    """)


def downgrade() -> None:
    # Not reversible in a meaningful way — manual posts could coexist.
    pass
