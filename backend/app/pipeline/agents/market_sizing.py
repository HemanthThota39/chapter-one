from __future__ import annotations

from typing import Any

from app.pipeline.agents.base import BaseAgent
from app.pipeline.research_engine import ResearchEngine
from app.prompts.library import PROMPT_2_MARKET_SIZING


class MarketSizingAgent(BaseAgent):
    name = "market_sizing"

    def __init__(self, llm, engine: ResearchEngine):
        super().__init__(llm)
        self.engine = engine

    async def run(self, metadata: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        queries = metadata.get("search_queries", {}).get("market_sizing", [])
        synthesis = PROMPT_2_MARKET_SIZING.format(
            idea_title=metadata.get("idea_title", ""),
            one_liner=metadata.get("one_liner", ""),
            industry=metadata.get("industry", ""),
            sub_sector=metadata.get("sub_sector", ""),
            target_customer=metadata.get("target_customer", {}),
            geography_focus=metadata.get("geography_focus", ""),
        )
        return await self.engine.run(
            agent=self.name,
            queries=queries,
            context=metadata,
            synthesis_prompt=synthesis,
        )
