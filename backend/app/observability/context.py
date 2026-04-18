"""ContextVar-based logger binding.

The pipeline binds an AnalysisLogger for the duration of one analysis run.
LLMClient and BaseAgent call get_logger() to retrieve it without needing
explicit parameter threading.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from app.observability.logger import AnalysisLogger

current_logger: ContextVar["AnalysisLogger | None"] = ContextVar(
    "analysis_logger", default=None
)


def get_logger() -> "AnalysisLogger | None":
    return current_logger.get()


@contextmanager
def bind_logger(logger: "AnalysisLogger") -> Iterator[None]:
    token = current_logger.set(logger)
    try:
        yield
    finally:
        current_logger.reset(token)
