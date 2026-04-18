from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core.llm import LLMClient
from app.core.progress import bus as progress_bus
from app.observability import AgentTrace, get_logger

log = logging.getLogger(__name__)


_AGENT_LABELS = {
    "orchestrator": "Classifying idea and planning research queries",
    "market_sizing": "Researching market size (TAM / SAM / SOM)",
    "competitive_intel": "Mapping competitors and funding signals",
    "news_trends": "Scanning news + timing signals",
    "regulatory": "Reviewing regulatory landscape",
    "problem_pmf": "Scoring problem severity and product-market fit",
    "business_model": "Evaluating business model and unit economics",
    "gtm_team": "Modelling go-to-market and team fit",
    "risk_moat": "Assessing competitive moat, traction, risk",
    "scoring": "Computing weighted CVF scorecard",
    "report_compiler": "Generating the markdown report",
}


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def _safe_run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Run inside an AgentTrace — logs start/complete/error + duration,
        and publishes a sub-step SSE detail so the UI can show what's running."""
        logger = get_logger()
        label = _AGENT_LABELS.get(self.name, self.name)
        if logger:
            try:
                await progress_bus.publish_detail(logger.analysis_id, label)
            except Exception:  # noqa: BLE001
                pass
        try:
            async with AgentTrace(self.name):
                return await self.run(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            log.exception("%s agent failed", self.name)
            return {"error": str(e), "agent": self.name}
