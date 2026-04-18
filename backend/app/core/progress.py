from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Literal


@dataclass
class ProgressEvent:
    stage: str
    percent: int
    message: str = ""
    kind: Literal["progress", "detail"] = "progress"


class ProgressBus:
    """In-memory pub/sub keyed by analysis_id.

    Two event kinds:
      - 'progress': coarse pipeline stages (drives the progress bar)
      - 'detail':   sub-step activity (drives a one-liner subtitle)

    Single-process only — fine for local dev.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[ProgressEvent | None]] = {}

    def register(self, analysis_id: str) -> asyncio.Queue[ProgressEvent | None]:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        self._queues[analysis_id] = queue
        return queue

    async def publish(self, analysis_id: str, event: ProgressEvent) -> None:
        queue = self._queues.get(analysis_id)
        if queue is not None:
            await queue.put(event)

    async def publish_detail(
        self, analysis_id: str, message: str, stage: str = "", percent: int = -1
    ) -> None:
        """Emit a transient sub-step event — shown to the user as a one-liner.
        The progress bar does NOT advance on detail events."""
        queue = self._queues.get(analysis_id)
        if queue is not None:
            await queue.put(
                ProgressEvent(stage=stage, percent=percent, message=message, kind="detail")
            )

    async def close(self, analysis_id: str) -> None:
        queue = self._queues.get(analysis_id)
        if queue is not None:
            await queue.put(None)

    def drop(self, analysis_id: str) -> None:
        self._queues.pop(analysis_id, None)

    async def stream(self, analysis_id: str) -> AsyncIterator[ProgressEvent]:
        queue = self._queues.get(analysis_id)
        if queue is None:
            return
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event


bus = ProgressBus()
