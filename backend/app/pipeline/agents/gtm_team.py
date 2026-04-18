from __future__ import annotations

from typing import Any

from app.pipeline.agents.base import BaseAgent
from app.pipeline.context import ResearchBundle
from app.prompts.library import PROMPT_0_SYSTEM, PROMPT_8_GTM_TEAM


class GtmTeamAgent(BaseAgent):
    name = "gtm_team"

    async def run(self, research: ResearchBundle) -> dict[str, Any]:  # type: ignore[override]
        user = PROMPT_8_GTM_TEAM.format(all_research_context=research.as_context_blob())
        return await self.llm.chat_json(system=PROMPT_0_SYSTEM, user=user, agent=self.name)
