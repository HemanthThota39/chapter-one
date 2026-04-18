"""posts, comments, fires, notifications + triggers

Revision ID: 0004_social
Revises: 0003_analyses_core
Create Date: 2026-04-18 19:00:00 UTC

Adds the M3 social surface:
  posts           — 1:1 with public analyses; denormalised counts
  comments        — flat-with-parent threaded; soft-delete only for
                    preserving reply context; hard-delete on user delete
  fires           — (user, post) composite PK; toggle semantics
  notifications   — in-app only, read_at for 30-day auto-cleanup

Trigger-based denormalization maintains posts.fire_count,
posts.comment_count, and users.fires_received automatically.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_social"
down_revision: Union[str, None] = "0003_analyses_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # posts
    op.execute("""
        CREATE TABLE posts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id     UUID NOT NULL UNIQUE REFERENCES analyses(id) ON DELETE CASCADE,
            owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            caption         TEXT CHECK (char_length(caption) <= 500),
            published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            fire_count      INTEGER NOT NULL DEFAULT 0,
            comment_count   INTEGER NOT NULL DEFAULT 0
        );
    """)
    op.execute("CREATE INDEX idx_posts_published   ON posts (published_at DESC);")
    op.execute("CREATE INDEX idx_posts_owner       ON posts (owner_id, published_at DESC);")

    # comments
    op.execute("""
        CREATE TABLE comments (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id      UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            author_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            parent_id    UUID REFERENCES comments(id) ON DELETE CASCADE,
            body         TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 1000),
            is_edited    BOOLEAN NOT NULL DEFAULT FALSE,
            is_deleted   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            edited_at    TIMESTAMPTZ
        );
    """)
    op.execute("CREATE INDEX idx_comments_post    ON comments (post_id, created_at);")
    op.execute("CREATE INDEX idx_comments_parent  ON comments (parent_id) WHERE parent_id IS NOT NULL;")

    # fires
    op.execute("""
        CREATE TABLE fires (
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            post_id      UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, post_id)
        );
    """)
    op.execute("CREATE INDEX idx_fires_post ON fires (post_id);")

    # notifications
    op.execute("""
        CREATE TABLE notifications (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind         TEXT NOT NULL,
            payload      JSONB NOT NULL,
            read_at      TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_notifications_user_unread ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;")
    op.execute("CREATE INDEX idx_notifications_user_all    ON notifications (user_id, created_at DESC);")
    op.execute("CREATE INDEX idx_notifications_expiry      ON notifications (read_at) WHERE read_at IS NOT NULL;")

    # Trigger: keep posts.fire_count + users.fires_received in sync with fires rows
    op.execute("""
        CREATE OR REPLACE FUNCTION fires_count_bump() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            UPDATE posts SET fire_count = fire_count + 1 WHERE id = NEW.post_id;
            UPDATE users SET fires_received = fires_received + 1
              WHERE id = (SELECT owner_id FROM posts WHERE id = NEW.post_id);
          ELSIF TG_OP = 'DELETE' THEN
            UPDATE posts SET fire_count = GREATEST(0, fire_count - 1) WHERE id = OLD.post_id;
            UPDATE users SET fires_received = GREATEST(0, fires_received - 1)
              WHERE id = (SELECT owner_id FROM posts WHERE id = OLD.post_id);
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_fires_count
        AFTER INSERT OR DELETE ON fires
        FOR EACH ROW EXECUTE FUNCTION fires_count_bump();
    """)

    # Trigger: keep posts.comment_count in sync (only live comments — is_deleted=false)
    op.execute("""
        CREATE OR REPLACE FUNCTION comments_count_bump() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'INSERT' AND NOT NEW.is_deleted THEN
            UPDATE posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
          ELSIF TG_OP = 'DELETE' AND NOT OLD.is_deleted THEN
            UPDATE posts SET comment_count = GREATEST(0, comment_count - 1) WHERE id = OLD.post_id;
          ELSIF TG_OP = 'UPDATE' THEN
            IF OLD.is_deleted = FALSE AND NEW.is_deleted = TRUE THEN
              UPDATE posts SET comment_count = GREATEST(0, comment_count - 1) WHERE id = NEW.post_id;
            ELSIF OLD.is_deleted = TRUE AND NEW.is_deleted = FALSE THEN
              UPDATE posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
            END IF;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_comments_count
        AFTER INSERT OR UPDATE OR DELETE ON comments
        FOR EACH ROW EXECUTE FUNCTION comments_count_bump();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_comments_count ON comments;")
    op.execute("DROP FUNCTION IF EXISTS comments_count_bump();")
    op.execute("DROP TRIGGER IF EXISTS trg_fires_count ON fires;")
    op.execute("DROP FUNCTION IF EXISTS fires_count_bump();")
    op.execute("DROP TABLE IF EXISTS notifications;")
    op.execute("DROP TABLE IF EXISTS fires;")
    op.execute("DROP TABLE IF EXISTS comments;")
    op.execute("DROP TABLE IF EXISTS posts;")
