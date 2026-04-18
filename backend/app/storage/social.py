"""Persistence for the M3 social surface: posts, comments, fires, notifications."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.db import transaction

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------

async def create_post_if_missing(analysis_id: str, owner_id: str, caption: str | None = None) -> str | None:
    """Called by the worker when an analysis completes with visibility=public.
    Idempotent — if post already exists, returns its id; else creates."""
    async with transaction() as conn:
        row = await conn.fetchrow(
            """INSERT INTO posts (analysis_id, owner_id, caption)
                    VALUES ($1::uuid, $2::uuid, $3)
               ON CONFLICT (analysis_id) DO NOTHING
                 RETURNING id""",
            analysis_id, owner_id, caption,
        )
        if row is None:
            row = await conn.fetchrow("SELECT id FROM posts WHERE analysis_id = $1::uuid", analysis_id)
        return str(row["id"]) if row else None


async def delete_post_for_analysis(analysis_id: str) -> None:
    async with transaction() as conn:
        await conn.execute("DELETE FROM posts WHERE analysis_id = $1::uuid", analysis_id)


async def update_post_caption(post_id: str, owner_id: str, caption: str | None) -> bool:
    async with transaction() as conn:
        row = await conn.execute(
            """UPDATE posts SET caption = $3
                WHERE id = $1::uuid AND owner_id = $2::uuid""",
            post_id, owner_id, caption,
        )
    return row.endswith(" 1")


async def list_feed(
    *, viewer_id: str | None, cursor: str | None, limit: int = 20,
) -> tuple[list[dict[str, Any]], str | None]:
    """Global chronological feed of public posts.
    Cursor = last-seen published_at ISO timestamp.
    """
    args: list[Any] = []
    where = "WHERE a.visibility = 'public' AND a.status = 'done'"
    if cursor:
        args.append(cursor)
        where += f" AND p.published_at < ${len(args)}::timestamptz"
    args.append(limit + 1)
    sql = f"""
        SELECT p.id AS post_id, p.analysis_id, p.caption, p.published_at,
               p.fire_count, p.comment_count,
               a.idea_title, a.slug, a.verdict, a.overall_score_100,
               u.id AS owner_id, u.username, u.display_name, u.avatar_url,
               u.avatar_kind, u.avatar_seed,
               EXISTS (
                 SELECT 1 FROM fires f
                 WHERE f.post_id = p.id AND f.user_id = $0::uuid
               ) AS i_fired_bool
        FROM posts p
        JOIN analyses a ON a.id = p.analysis_id
        JOIN users u    ON u.id = p.owner_id
        {where}
        ORDER BY p.published_at DESC
        LIMIT ${len(args)}
    """
    # Fix $0 placeholder: asyncpg uses 1-based params; embed viewer id as $1
    # Rebuild the query more cleanly
    final_args: list[Any] = [viewer_id]
    where2 = "WHERE a.visibility = 'public' AND a.status = 'done'"
    if cursor:
        final_args.append(cursor)
        where2 += f" AND p.published_at < ${len(final_args)}::timestamptz"
    final_args.append(limit + 1)
    sql = f"""
        SELECT p.id AS post_id, p.analysis_id, p.caption, p.published_at,
               p.fire_count, p.comment_count,
               a.idea_title, a.slug, a.verdict, a.overall_score_100,
               u.id AS owner_id, u.username, u.display_name, u.avatar_url,
               u.avatar_kind, u.avatar_seed,
               CASE
                 WHEN $1::uuid IS NULL THEN FALSE
                 ELSE EXISTS (SELECT 1 FROM fires f WHERE f.post_id = p.id AND f.user_id = $1::uuid)
               END AS i_fired_bool
          FROM posts p
          JOIN analyses a ON a.id = p.analysis_id
          JOIN users u    ON u.id = p.owner_id
          {where2}
         ORDER BY p.published_at DESC
         LIMIT ${len(final_args)}
    """
    async with transaction() as conn:
        rows = await conn.fetch(sql, *final_args)

    items = [dict(r) for r in rows[:limit]]
    next_cursor = items[-1]["published_at"].isoformat() if len(rows) > limit and items else None
    return items, next_cursor


async def get_post(post_id: str, *, viewer_id: str | None) -> dict[str, Any] | None:
    async with transaction() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.id AS post_id, p.analysis_id, p.caption, p.published_at,
                   p.fire_count, p.comment_count,
                   a.idea_title, a.slug, a.verdict, a.overall_score_100, a.visibility,
                   u.id AS owner_id, u.username, u.display_name, u.avatar_url,
                   u.avatar_kind, u.avatar_seed,
                   CASE
                     WHEN $2::uuid IS NULL THEN FALSE
                     ELSE EXISTS (SELECT 1 FROM fires f WHERE f.post_id = p.id AND f.user_id = $2::uuid)
                   END AS i_fired_bool
              FROM posts p
              JOIN analyses a ON a.id = p.analysis_id
              JOIN users u    ON u.id = p.owner_id
             WHERE p.id = $1::uuid
            """,
            post_id, viewer_id,
        )
    return dict(row) if row else None


# ---------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------

async def create_comment(
    *, post_id: str, author_id: str, body: str, parent_id: str | None,
) -> dict[str, Any]:
    async with transaction() as conn:
        row = await conn.fetchrow(
            """INSERT INTO comments (post_id, author_id, parent_id, body)
                    VALUES ($1::uuid, $2::uuid, $3::uuid, $4)
                 RETURNING id, post_id, author_id, parent_id, body, is_edited,
                           is_deleted, created_at, edited_at""",
            post_id, author_id, parent_id, body,
        )
    return dict(row)


async def list_comments(post_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    async with transaction() as conn:
        rows = await conn.fetch(
            """SELECT c.id, c.post_id, c.parent_id, c.body, c.is_edited,
                      c.is_deleted, c.created_at, c.edited_at,
                      u.id AS author_id, u.username, u.display_name, u.avatar_url,
                      u.avatar_kind, u.avatar_seed
                 FROM comments c
                 JOIN users u ON u.id = c.author_id
                WHERE c.post_id = $1::uuid
             ORDER BY c.created_at ASC
                LIMIT $2""",
            post_id, limit,
        )
    return [dict(r) for r in rows]


async def edit_comment(comment_id: str, author_id: str, body: str) -> bool:
    async with transaction() as conn:
        result = await conn.execute(
            """UPDATE comments
                  SET body = $3, is_edited = TRUE, edited_at = NOW()
                WHERE id = $1::uuid AND author_id = $2::uuid AND is_deleted = FALSE""",
            comment_id, author_id, body,
        )
    return result.endswith(" 1")


async def soft_delete_comment(comment_id: str, user_id: str) -> bool:
    """Author or post owner can delete. Soft-delete preserves thread context."""
    async with transaction() as conn:
        result = await conn.execute(
            """UPDATE comments c
                  SET is_deleted = TRUE, body = '[deleted]'
                 FROM posts p
                WHERE c.id = $1::uuid
                  AND p.id = c.post_id
                  AND (c.author_id = $2::uuid OR p.owner_id = $2::uuid)""",
            comment_id, user_id,
        )
    return result.endswith(" 1")


# ---------------------------------------------------------------------
# Fires
# ---------------------------------------------------------------------

async def toggle_fire(user_id: str, post_id: str) -> tuple[bool, int]:
    """Returns (is_fired_now, new_total). Idempotent toggle."""
    async with transaction() as conn:
        existing = await conn.fetchrow(
            "SELECT 1 FROM fires WHERE user_id = $1::uuid AND post_id = $2::uuid",
            user_id, post_id,
        )
        if existing:
            await conn.execute(
                "DELETE FROM fires WHERE user_id = $1::uuid AND post_id = $2::uuid",
                user_id, post_id,
            )
            is_fired = False
        else:
            await conn.execute(
                "INSERT INTO fires (user_id, post_id) VALUES ($1::uuid, $2::uuid)",
                user_id, post_id,
            )
            is_fired = True
        count = await conn.fetchval(
            "SELECT fire_count FROM posts WHERE id = $1::uuid", post_id,
        )
    return is_fired, int(count or 0)


# ---------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------

async def emit_notification(user_id: str, kind: str, payload: dict[str, Any]) -> None:
    """Insert + fire NOTIFY on the user's channel for live badge updates."""
    async with transaction() as conn:
        await conn.execute(
            """INSERT INTO notifications (user_id, kind, payload)
                    VALUES ($1::uuid, $2, $3::jsonb)""",
            user_id, kind, json.dumps(payload, default=str),
        )
        channel = f"user_notifications_{str(user_id).replace('-', '_')}"
        body = json.dumps({"kind": kind})
        await conn.execute(f"NOTIFY {channel}, '{body[:7900]}'")


async def list_notifications(
    user_id: str, *, filter: str = "all", cursor: str | None = None, limit: int = 20,
) -> tuple[list[dict[str, Any]], int, str | None]:
    base = "WHERE user_id = $1::uuid"
    params: list[Any] = [user_id]
    if filter == "unread":
        base += " AND read_at IS NULL"
    if cursor:
        params.append(cursor)
        base += f" AND created_at < ${len(params)}::timestamptz"
    params.append(limit + 1)
    async with transaction() as conn:
        rows = await conn.fetch(
            f"""SELECT id, kind, payload, read_at, created_at
                  FROM notifications
                  {base}
              ORDER BY created_at DESC
                 LIMIT ${len(params)}""",
            *params,
        )
        unread = await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE user_id = $1::uuid AND read_at IS NULL",
            user_id,
        )
    items = [dict(r) for r in rows[:limit]]
    next_cursor = items[-1]["created_at"].isoformat() if len(rows) > limit and items else None
    return items, int(unread or 0), next_cursor


async def mark_notification_read(notification_id: str, user_id: str) -> bool:
    async with transaction() as conn:
        result = await conn.execute(
            """UPDATE notifications
                  SET read_at = NOW()
                WHERE id = $1::uuid AND user_id = $2::uuid AND read_at IS NULL""",
            notification_id, user_id,
        )
    return result.endswith(" 1")


async def mark_all_notifications_read(user_id: str) -> int:
    async with transaction() as conn:
        result = await conn.execute(
            """UPDATE notifications SET read_at = NOW()
                WHERE user_id = $1::uuid AND read_at IS NULL""",
            user_id,
        )
    try:
        return int(result.split()[-1])
    except Exception:
        return 0


async def delete_notification(notification_id: str, user_id: str) -> bool:
    async with transaction() as conn:
        result = await conn.execute(
            "DELETE FROM notifications WHERE id = $1::uuid AND user_id = $2::uuid",
            notification_id, user_id,
        )
    return result.endswith(" 1")


async def delete_all_notifications(user_id: str) -> int:
    async with transaction() as conn:
        result = await conn.execute(
            "DELETE FROM notifications WHERE user_id = $1::uuid", user_id,
        )
    try:
        return int(result.split()[-1])
    except Exception:
        return 0


def notify_channel(user_id: str) -> str:
    """Postgres NOTIFY channel name for a user's live notification stream."""
    return f"user_notifications_{str(user_id).replace('-', '_')}"
