from __future__ import annotations

from typing import Any

from app.pipeline.agents.base import BaseAgent
from app.prompts.library import PROMPT_0_SYSTEM, PROMPT_1_ORCHESTRATOR


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"

    async def run(self, idea_text: str) -> dict[str, Any]:  # type: ignore[override]
        user = PROMPT_1_ORCHESTRATOR.format(user_idea=idea_text)
        return await self.llm.chat_json(system=PROMPT_0_SYSTEM, user=user, agent=self.name)
