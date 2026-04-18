from __future__ import annotations

from typing import Any

from app.pipeline.agents.base import BaseAgent
from app.pipeline.context import ResearchBundle
from app.prompts.library import PROMPT_0_SYSTEM, PROMPT_7_BUSINESS_MODEL


class BusinessModelAgent(BaseAgent):
    name = "business_model"

    async def run(self, research: ResearchBundle) -> dict[str, Any]:  # type: ignore[override]
        user = PROMPT_7_BUSINESS_MODEL.format(all_research_context=research.as_context_blob())
        return await self.llm.chat_json(system=PROMPT_0_SYSTEM, user=user, agent=self.name)
