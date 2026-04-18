"""Context manager that wraps an agent's run() and logs start/complete/error."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.observability.context import get_logger

log = logging.getLogger(__name__)


class AgentTrace:
    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        self._started_at: float | None = None

    async def __aenter__(self) -> "AgentTrace":
        self._started_at = time.perf_counter()
        logger = get_logger()
        if logger:
            logger.event("agent.start", agent=self.agent_name)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        duration_ms = int((time.perf_counter() - (self._started_at or 0)) * 1000)
        logger = get_logger()
        if logger is None:
            return False
        if exc is not None:
            logger.event(
                "agent.error",
                agent=self.agent_name,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
                message=str(exc)[:500],
            )
        else:
            logger.event(
                "agent.complete",
                agent=self.agent_name,
                duration_ms=duration_ms,
            )
        return False  # never swallow exceptions
