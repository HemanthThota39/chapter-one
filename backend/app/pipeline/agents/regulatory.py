from __future__ import annotations

from typing import Any

from app.pipeline.agents.base import BaseAgent
from app.pipeline.research_engine import ResearchEngine
from app.prompts.library import PROMPT_5_REGULATORY


class RegulatoryAgent(BaseAgent):
    name = "regulatory"

    def __init__(self, llm, engine: ResearchEngine):
        super().__init__(llm)
        self.engine = engine

    async def run(self, metadata: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        queries = metadata.get("search_queries", {}).get("regulations", [])
        synthesis = PROMPT_5_REGULATORY.format(
            idea_title=metadata.get("idea_title", ""),
            industry=metadata.get("industry", ""),
            business_model_type=metadata.get("business_model_type", ""),
            geography_focus=metadata.get("geography_focus", ""),
        )
        return await self.engine.run(
            agent=self.name,
            queries=queries,
            context=metadata,
            synthesis_prompt=synthesis,
        )
