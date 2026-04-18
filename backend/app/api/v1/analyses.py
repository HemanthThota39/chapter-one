"""Analyses HTTP API.

POST   /api/v1/analyses                  — enqueue a job, return 202
GET    /api/v1/analyses                  — list current user's analyses
GET    /api/v1/analyses/{id}             — metadata
GET    /api/v1/analyses/{id}/stream      — SSE progress (LISTEN/NOTIFY driven)
GET    /api/v1/analyses/{id}/report      — markdown of current version
GET    /api/v1/analyses/{id}/report.pdf  — PDF of current version (download)
DELETE /api/v1/analyses/{id}             — delete (cascades)
"""

from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, constr
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import CurrentUser, OptionalCurrentUser
from app.core.queue import get_queue
from app.core.pdf import render_pdf, safe_filename
from app.db import get_pool
from app.storage import analyses as store
from app.storage import social

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


class SubmitAnalysisRequest(BaseModel):
    idea_text: constr(strip_whitespace=True, min_length=20, max_length=4000) = Field(...)
    visibility: str = Field("public", pattern=r"^(public|private)$")


class SubmitAnalysisResponse(BaseModel):
    analysis_id: str
    status: str = "queued"


@router.post("", response_model=SubmitAnalysisResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit(user: CurrentUser, req: SubmitAnalysisRequest) -> SubmitAnalysisResponse:
    # Require onboarding complete (need username for slug / public profile)
    if not user.username:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "complete_onboarding_first")

    analysis_id = await store.create_analysis(
        owner_id=user.id, idea_text=req.idea_text, visibility=req.visibility,
    )
    try:
        await get_queue().enqueue_analysis(analysis_id=analysis_id, owner_id=user.id)
    except Exception as e:
        log.exception("Failed to enqueue analysis")
        await store.mark_failed(analysis_id, f"enqueue_failed: {e}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "queue_unavailable")
    await store.publish_event(analysis_id, kind="progress", stage="queued", percent=0, message="Queued")
    return SubmitAnalysisResponse(analysis_id=analysis_id)


@router.get("")
async def list_mine(user: CurrentUser) -> dict:
    rows = await store.list_user_analyses(user.id, limit=50)
    items = []
    for r in rows:
        items.append({
            "id": str(r["id"]),
            "idea_title": r["idea_title"],
            "status": r["status"],
            "visibility": r["visibility"],
            "overall_score_100": r["overall_score_100"],
            "verdict": r["verdict"],
            "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
        })
    return {"items": items}


@router.get("/{analysis_id}")
async def get(analysis_id: str, user: OptionalCurrentUser) -> dict:
    row = await store.get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    is_owner = user is not None and str(user.id) == str(row["owner_id"])
    is_public = row["visibility"] == "public" and row["status"] == "done"
    if not (is_owner or is_public):
        # Don't leak existence
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return {
        "id": str(row["id"]),
        "owner": {
            "username": row["owner_username"],
            "display_name": row["owner_display_name"],
            "avatar_url": row["owner_avatar_url"],
        },
        "idea_title": row["idea_title"],
        "slug": row["slug"],
        "status": row["status"],
        "visibility": row["visibility"],
        "overall_score_100": row["overall_score_100"],
        "verdict": row["verdict"],
        "confidence": row["confidence"],
        "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "error_message": row["error_message"] if is_owner else None,
        "current_version_id": str(row["current_report_version_id"]) if row["current_report_version_id"] else None,
        "is_own": is_owner,
    }


@router.get("/{analysis_id}/stream")
async def stream(analysis_id: str, user: OptionalCurrentUser) -> EventSourceResponse:
    """SSE stream of progress events.
    Replay strategy: SELECT past events, then LISTEN on `analysis_{id}` for live ones.
    """
    row = await store.get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    is_owner = user is not None and str(user.id) == str(row["owner_id"])
    is_public = row["visibility"] == "public"
    if not (is_owner or is_public):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")

    channel = store._notify_channel(analysis_id)  # noqa: SLF001
    terminal_reached = False

    async def gen():
        nonlocal terminal_reached
        pool = await get_pool()
        # Dedicated connection for LISTEN (asyncpg shares channels on a connection)
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

            # Replay all past events first
            past = await store.fetch_past_events(analysis_id)
            for e in past:
                data = {"stage": e["stage"], "percent": e["percent"], "message": e["message"]}
                yield {"event": e["kind"] or "progress", "data": json.dumps(data)}
                if e["kind"] == "progress" and e["stage"] in {"done", "error"}:
                    terminal_reached = True

            if terminal_reached:
                yield {"event": "close", "data": "{}"}
                return

            # Stream live events
            heartbeat_interval = 20
            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                kind = event_data.get("kind", "progress")
                yield {
                    "event": kind,
                    "data": json.dumps({
                        "stage": event_data.get("stage"),
                        "percent": event_data.get("percent"),
                        "message": event_data.get("message"),
                    }),
                }
                if kind == "progress" and event_data.get("stage") in {"done", "error"}:
                    yield {"event": "close", "data": "{}"}
                    return
        finally:
            try:
                await conn.remove_listener(channel, _on_notify)
            except Exception:
                pass
            await pool.release(conn)

    return EventSourceResponse(gen())


@router.get("/{analysis_id}/report")
async def report(analysis_id: str, user: OptionalCurrentUser, version: str | None = None):
    row = await store.get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    is_owner = user is not None and str(user.id) == str(row["owner_id"])
    is_public = row["visibility"] == "public" and row["status"] == "done"
    if not (is_owner or is_public):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    md = await store.render_report_markdown(analysis_id, version_id=version)
    if md is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report_not_ready")
    return Response(content=md, media_type="text/markdown; charset=utf-8")


@router.get("/{analysis_id}/report.pdf")
async def report_pdf(analysis_id: str, user: OptionalCurrentUser, version: str | None = None):
    row = await store.get_analysis(analysis_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    is_owner = user is not None and str(user.id) == str(row["owner_id"])
    is_public = row["visibility"] == "public" and row["status"] == "done"
    if not (is_owner or is_public):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    md = await store.render_report_markdown(analysis_id, version_id=version)
    if md is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report_not_ready")

    completed = row.get("completed_at")
    generated_at = completed.strftime("%d %b %Y") if completed else None

    try:
        # weasyprint is synchronous and CPU-bound; keep the event loop free.
        pdf_bytes = await asyncio.to_thread(
            render_pdf,
            md,
            title=row.get("idea_title"),
            verdict=row.get("verdict"),
            score=row.get("overall_score_100"),
            author=None,
            generated_at=generated_at,
        )
    except Exception:
        log.exception("pdf render failed for analysis %s", analysis_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "pdf_render_failed") from None

    filename = safe_filename(row.get("idea_title"), fallback=f"analysis-{analysis_id[:8]}") + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


class PatchAnalysisRequest(BaseModel):
    visibility: str | None = Field(None, pattern=r"^(public|private)$")
    caption: constr(strip_whitespace=True, max_length=500) | None = None


@router.patch("/{analysis_id}")
async def patch(analysis_id: str, user: CurrentUser, req: PatchAnalysisRequest) -> dict:
    row = await store.get_analysis(analysis_id)
    if row is None or str(row["owner_id"]) != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")

    pool = await get_pool()
    async with pool.acquire() as conn:
        if req.visibility is not None and req.visibility != row["visibility"]:
            await conn.execute(
                "UPDATE analyses SET visibility = $2 WHERE id = $1::uuid",
                analysis_id, req.visibility,
            )
            if req.visibility == "public" and row["status"] == "done":
                await social.create_post_if_missing(analysis_id, str(row["owner_id"]), caption=req.caption)
            elif req.visibility == "private":
                await social.delete_post_for_analysis(analysis_id)

        if req.caption is not None and row["visibility"] == "public":
            await conn.execute(
                "UPDATE posts SET caption = $2 WHERE analysis_id = $1::uuid",
                analysis_id, req.caption,
            )

    return await get(analysis_id, user)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(analysis_id: str, user: CurrentUser) -> Response:
    row = await store.get_analysis(analysis_id)
    if row is None or str(row["owner_id"]) != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM analyses WHERE id=$1::uuid", analysis_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
