"""In-memory fallback store.

Used when Postgres isn't available. Keeps last N completed reports so
the download endpoint works without infra.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from app.pipeline.pipeline import PipelineResult


class MemoryStore:
    def __init__(self, capacity: int = 50) -> None:
        self._capacity = capacity
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def save(self, result: PipelineResult) -> None:
        scoring = result.scoring or {}
        title = result.orchestrator.get("idea_title") if result.orchestrator else None
        self._items[result.analysis_id] = {
            "id": result.analysis_id,
            "idea_text": result.idea_text,
            "idea_title": title,
            "overall_score_100": scoring.get("overall_score_100"),
            "verdict": scoring.get("verdict"),
            "markdown": result.markdown,
            "created_at": datetime.now(timezone.utc),
        }
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)

    def get_markdown(self, analysis_id: str) -> str | None:
        item = self._items.get(analysis_id)
        return item["markdown"] if item else None

    def get_meta(self, analysis_id: str) -> dict[str, Any] | None:
        item = self._items.get(analysis_id)
        if not item:
            return None
        meta = dict(item)
        meta.pop("markdown", None)
        return meta


memory_store = MemoryStore()
