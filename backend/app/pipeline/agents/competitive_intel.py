from __future__ import annotations

from typing import Any

from app.pipeline.agents.base import BaseAgent
from app.pipeline.research_engine import ResearchEngine
from app.prompts.library import PROMPT_3_COMPETITIVE


class CompetitiveIntelAgent(BaseAgent):
    name = "competitive_intel"

    def __init__(self, llm, engine: ResearchEngine):
        super().__init__(llm)
        self.engine = engine

    async def run(self, metadata: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        queries = metadata.get("search_queries", {}).get("competitors", [])
        synthesis = PROMPT_3_COMPETITIVE.format(
            idea_title=metadata.get("idea_title", ""),
            one_liner=metadata.get("one_liner", ""),
            industry=metadata.get("industry", ""),
            target_customer=metadata.get("target_customer", {}),
        )
        return await self.engine.run(
            agent=self.name,
            queries=queries,
            context=metadata,
            synthesis_prompt=synthesis,
        )
