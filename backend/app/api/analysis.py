from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from sse_starlette.sse import EventSourceResponse

from app.core.llm import LLMClient
from app.core.progress import ProgressEvent, bus
from app.models.schemas import AnalysisRequest, AnalysisStartResponse
from app.pipeline.pipeline import StartupAnalysisPipeline
from app.storage.memory import memory_store
from app.storage.repository import AnalysisRepository

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_llm = LLMClient()
_pipeline = StartupAnalysisPipeline(_llm)
_repo = AnalysisRepository()


async def _run_and_persist(analysis_id: str, idea: str) -> None:
    try:
        result = await _pipeline.run(analysis_id, idea)
        # Always save to memory — survives DB outages.
        memory_store.save(result)
        # Best-effort DB write.
        try:
            await _repo.save(result)
        except Exception:
            log.warning(
                "DB unavailable for %s — report kept in memory only", analysis_id
            )
    except Exception as e:
        log.exception("Pipeline failed for %s", analysis_id)
        await bus.publish(
            analysis_id, ProgressEvent(stage="error", percent=100, message=str(e))
        )
    finally:
        await bus.close(analysis_id)


@router.post("", response_model=AnalysisStartResponse)
async def start_analysis(
    payload: AnalysisRequest, background: BackgroundTasks
) -> AnalysisStartResponse:
    analysis_id = _pipeline.new_analysis_id()
    bus.register(analysis_id)
    background.add_task(_run_and_persist, analysis_id, payload.idea)
    return AnalysisStartResponse(analysis_id=analysis_id, status="queued")


@router.get("/{analysis_id}/stream")
async def stream_progress(analysis_id: str) -> EventSourceResponse:
    async def event_generator():
        try:
            async for event in bus.stream(analysis_id):
                event_name = event.kind  # 'progress' or 'detail'
                yield {
                    "event": event_name,
                    "data": json.dumps(
                        {
                            "stage": event.stage,
                            "percent": event.percent,
                            "message": event.message,
                        }
                    ),
                }
                # Only terminal progress events end the stream.
                if event.kind == "progress" and event.stage in {"done", "error"}:
                    break
            yield {"event": "close", "data": "{}"}
        finally:
            bus.drop(analysis_id)

    return EventSourceResponse(event_generator())


async def _load_markdown(analysis_id: str) -> str | None:
    md = memory_store.get_markdown(analysis_id)
    if md is not None:
        return md
    try:
        return await _repo.get_markdown(analysis_id)
    except Exception:
        log.debug("DB lookup skipped (unavailable)")
        return None


@router.get("/{analysis_id}/report")
async def get_report(analysis_id: str) -> Response:
    markdown = await _load_markdown(analysis_id)
    if markdown is None:
        for _ in range(50):
            await asyncio.sleep(0.1)
            markdown = await _load_markdown(analysis_id)
            if markdown is not None:
                break
    if markdown is None:
        raise HTTPException(status_code=404, detail="Report not found or still running")
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="analysis-{analysis_id}.md"'
        },
    )


@router.get("/{analysis_id}")
async def get_meta(analysis_id: str):
    meta = memory_store.get_meta(analysis_id)
    if meta is None:
        try:
            meta = await _repo.get_meta(analysis_id)
        except Exception:
            meta = None
    if meta is None:
        raise HTTPException(status_code=404, detail="Not found")
    if hasattr(meta.get("id"), "hex"):
        meta["id"] = str(meta["id"])
    created = meta.get("created_at")
    if hasattr(created, "isoformat"):
        meta["created_at"] = created.isoformat()
    return meta
