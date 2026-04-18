"""Telemetry endpoints — receive client-side errors (e.g. Mermaid render)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.observability import AnalysisLogger

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


class RenderErrorPayload(BaseModel):
    analysis_id: str
    chart_index: int = Field(..., ge=0)
    error: str
    code: str = ""
    kind: Literal["mermaid", "markdown"] = "mermaid"


@router.post("/render-error")
async def render_error(payload: RenderErrorPayload) -> dict[str, str]:
    settings = get_settings()
    log_dir = Path(settings.log_dir) / payload.analysis_id
    if not log_dir.exists():
        raise HTTPException(status_code=404, detail="Unknown analysis_id")

    logger = AnalysisLogger(
        analysis_id=payload.analysis_id,
        log_dir=Path(settings.log_dir),
        log_raw_responses=False,
    )
    logger.event(
        "render.mermaid_error" if payload.kind == "mermaid" else "render.markdown_error",
        chart_index=payload.chart_index,
        error=payload.error[:500],
        code=payload.code[:2000],
    )
    # Also dump the exact offending code to the raw/ dir for deep inspection.
    try:
        dump_dir = log_dir / "raw"
        dump_dir.mkdir(parents=True, exist_ok=True)
        (dump_dir / f"broken_{payload.kind}_{payload.chart_index}.txt").write_text(
            payload.code, encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        log.exception("Failed to dump render error code")

    return {"status": "logged"}
