"""Per-analysis structured logger.

Writes:
  logs/<analysis_id>/events.jsonl   — one JSON event per line
  logs/<analysis_id>/raw/<agent>.json — full LLM response (if LOG_RAW_RESPONSES)
  logs/<analysis_id>/summary.md     — human-readable summary (built at end of run)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class AnalysisLogger:
    """File-backed structured logger scoped to one analysis run."""

    def __init__(
        self,
        analysis_id: str,
        log_dir: Path,
        *,
        log_raw_responses: bool = True,
    ) -> None:
        self.analysis_id = analysis_id
        self.dir = Path(log_dir) / analysis_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.raw_dir = self.dir / "raw"
        self.log_raw_responses = log_raw_responses
        self._lock = threading.Lock()

    def event(self, event_type: str, **fields: Any) -> None:
        """Append one JSON event to events.jsonl. Never raises."""
        try:
            record = {
                "ts": time.time(),
                "event": event_type,
                "analysis_id": self.analysis_id,
                **fields,
            }
            line = json.dumps(record, default=_json_default, ensure_ascii=False)
            with self._lock, self.events_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:  # noqa: BLE001
            log.exception("AnalysisLogger.event failed (event_type=%s)", event_type)

    def save_raw(self, agent_name: str, payload: Any) -> None:
        """Dump full agent response JSON to raw/<agent>.json (if enabled)."""
        if not self.log_raw_responses:
            return
        try:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            path = self.raw_dir / f"{agent_name}.json"
            path.write_text(
                json.dumps(payload, indent=2, default=_json_default, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            log.exception("AnalysisLogger.save_raw failed (agent=%s)", agent_name)

    def write_summary(self, markdown: str) -> None:
        """Write the human-readable summary.md."""
        try:
            (self.dir / "summary.md").write_text(markdown, encoding="utf-8")
        except Exception:  # noqa: BLE001
            log.exception("AnalysisLogger.write_summary failed")


def _json_default(o: Any) -> Any:
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)
