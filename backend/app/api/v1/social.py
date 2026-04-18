"""Social HTTP API — feed, posts, comments, fires, notifications."""

from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, constr
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import CurrentUser, OptionalCurrentUser
from app.db import get_pool
from app.storage import social

log = logging.getLogger(__name__)

feed_router = APIRouter(prefix="/api/v1", tags=["social"])


# ---------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------
@feed_router.get("/feed")
async def get_feed(
    user: CurrentUser,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    items, next_cursor = await social.list_feed(viewer_id=user.id, cursor=cursor, limit=limit)
    return {
        "items": [_serialize_feed_item(r) for r in items],
        "next_cursor": next_cursor,
    }


@feed_router.get("/posts/{post_id}")
async def get_post(post_id: str, user: OptionalCurrentUser) -> dict:
    viewer_id = user.id if user else None
    row = await social.get_post(post_id, viewer_id=viewer_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    if row["visibility"] != "public" and (user is None or str(user.id) != str(row["owner_id"])):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return _serialize_feed_item(row)


# ---------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------
class CommentCreate(BaseModel):
    body: constr(strip_whitespace=True, min_length=1, max_length=1000) = Field(...)
    parent_id: str | None = None


@feed_router.get("/posts/{post_id}/comments")
async def list_comments(post_id: str, user: OptionalCurrentUser) -> dict:
    row = await social.get_post(post_id, viewer_id=user.id if user else None)
    if row is None or (row["visibility"] != "public" and (user is None or str(user.id) != str(row["owner_id"]))):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    comments = await social.list_comments(post_id)
    return {"items": [_serialize_comment(c) for c in comments]}


@feed_router.post("/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
async def create_comment(post_id: str, user: CurrentUser, req: CommentCreate) -> dict:
    post = await social.get_post(post_id, viewer_id=user.id)
    if post is None or post["visibility"] != "public":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")

    comment = await social.create_comment(
        post_id=post_id,
        author_id=user.id,
        body=req.body,
        parent_id=req.parent_id,
    )

    # Emit notifications (own-post comments don't notify yourself)
    post_owner_id = str(post["owner_id"])
    if post_owner_id != user.id:
        await social.emit_notification(
            post_owner_id,
            "comment",
            {
                "post_id": post_id,
                "analysis_id": str(post["analysis_id"]),
                "comment_id": str(comment["id"]),
                "actor_username": user.username,
                "preview": req.body[:80],
            },
        )
    if req.parent_id:
        parent_row = await _get_comment_author(req.parent_id)
        if parent_row and str(parent_row) != user.id and str(parent_row) != post_owner_id:
            await social.emit_notification(
                str(parent_row),
                "reply",
                {
                    "post_id": post_id,
                    "analysis_id": str(post["analysis_id"]),
                    "comment_id": str(comment["id"]),
                    "parent_id": req.parent_id,
                    "actor_username": user.username,
                    "preview": req.body[:80],
                },
            )

    # Attach author info for the response
    comment["username"] = user.username
    comment["display_name"] = None  # client already has it via session; skip extra read
    return {"comment": _serialize_comment(comment)}


@feed_router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(comment_id: str, user: CurrentUser) -> Response:
    ok = await social.soft_delete_comment(comment_id, user.id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found_or_forbidden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _get_comment_author(comment_id: str) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT author_id FROM comments WHERE id = $1::uuid",
            comment_id,
        )
    return str(row["author_id"]) if row else None


# ---------------------------------------------------------------------
# Fires
# ---------------------------------------------------------------------
@feed_router.post("/posts/{post_id}/fires")
async def toggle_fire(post_id: str, user: CurrentUser) -> dict:
    post = await social.get_post(post_id, viewer_id=user.id)
    if post is None or post["visibility"] != "public":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")

    fired, count = await social.toggle_fire(user.id, post_id)
    # Notify the post owner only when we just added a fire (not on un-fire) and not self
    owner_id = str(post["owner_id"])
    if fired and owner_id != user.id:
        await social.emit_notification(
            owner_id,
            "fire",
            {
                "post_id": post_id,
                "analysis_id": str(post["analysis_id"]),
                "actor_username": user.username,
            },
        )
    return {"fired": fired, "fire_count": count}


# ---------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------
notif_router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@notif_router.get("")
async def list_notifications(
    user: CurrentUser,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    filter: str = Query("all", pattern="^(all|unread)$"),
) -> dict:
    items, unread, next_cursor = await social.list_notifications(
        user.id, filter=filter, cursor=cursor, limit=limit,
    )
    return {
        "items": [_serialize_notif(n) for n in items],
        "unread_count": unread,
        "next_cursor": next_cursor,
    }


@notif_router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: str, user: CurrentUser) -> Response:
    ok = await social.mark_notification_read(notification_id, user.id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@notif_router.post("/read-all")
async def mark_all_read(user: CurrentUser) -> dict:
    marked = await social.mark_all_notifications_read(user.id)
    return {"marked": marked}


@notif_router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one(notification_id: str, user: CurrentUser) -> Response:
    ok = await social.delete_notification(notification_id, user.id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@notif_router.delete("")
async def delete_all(user: CurrentUser) -> dict:
    n = await social.delete_all_notifications(user.id)
    return {"cleared": n}


@notif_router.get("/stream")
async def stream(user: CurrentUser):
    """SSE stream: emits 'new' events when a notification lands for this user.
    The client uses this to live-update the unread badge + list.
    """
    channel = social.notify_channel(user.id)

    async def gen():
        pool = await get_pool()
        conn: asyncpg.Connection = await pool.acquire()
        queue: asyncio.Queue[dict] = asyncio.Queue()

        def _on_notify(connection, pid, ch, payload):
            try:
                data = json.loads(payload) if payload else {}
            except Exception:
                data = {"raw": payload}
            queue.put_nowait(data)

        try:
            await conn.add_listener(channel, _on_notify)
            # Emit initial unread count
            _items, unread, _ = await social.list_notifications(user.id, filter="unread", limit=1)
            yield {"event": "unread_count", "data": json.dumps({"unread_count": unread})}

            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "new", "data": json.dumps(event_data)}
                _items, unread, _ = await social.list_notifications(user.id, filter="unread", limit=1)
                yield {"event": "unread_count", "data": json.dumps({"unread_count": unread})}
        finally:
            try:
                await conn.remove_listener(channel, _on_notify)
            except Exception:
                pass
            await pool.release(conn)

    return EventSourceResponse(gen())


# ---------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------

def _serialize_feed_item(r: dict) -> dict:
    return {
        "post_id": str(r["post_id"]),
        "analysis_id": str(r["analysis_id"]),
        "owner": {
            "id": str(r["owner_id"]),
            "username": r["username"],
            "display_name": r["display_name"],
            "avatar_url": r["avatar_url"],
            "avatar_kind": r["avatar_kind"],
            "avatar_seed": r["avatar_seed"],
        },
        "idea_title": r["idea_title"],
        "slug": r.get("slug"),
        "verdict": r["verdict"],
        "overall_score_100": r["overall_score_100"],
        "caption": r["caption"],
        "published_at": r["published_at"].isoformat() if r["published_at"] else None,
        "fire_count": r["fire_count"],
        "comment_count": r["comment_count"],
        "i_fired": bool(r.get("i_fired_bool")),
    }


def _serialize_comment(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "post_id": str(r.get("post_id")) if r.get("post_id") else None,
        "parent_id": str(r["parent_id"]) if r.get("parent_id") else None,
        "body": r["body"],
        "is_edited": bool(r.get("is_edited")),
        "is_deleted": bool(r.get("is_deleted")),
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "edited_at": r["edited_at"].isoformat() if r.get("edited_at") else None,
        "author": {
            "id": str(r["author_id"]) if r.get("author_id") else None,
            "username": r.get("username"),
            "display_name": r.get("display_name"),
            "avatar_url": r.get("avatar_url"),
            "avatar_kind": r.get("avatar_kind"),
            "avatar_seed": r.get("avatar_seed"),
        },
    }


def _serialize_notif(n: dict) -> dict:
    payload = n["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass
    return {
        "id": str(n["id"]),
        "kind": n["kind"],
        "payload": payload,
        "read_at": n["read_at"].isoformat() if n["read_at"] else None,
        "created_at": n["created_at"].isoformat() if n["created_at"] else None,
    }
