from __future__ import annotations

import json
from typing import Any

from app.pipeline.agents.base import BaseAgent
from app.pipeline.context import AnalysisBundle
from app.prompts.library import PROMPT_0_SYSTEM, PROMPT_10_SCORING


class ScoringAgent(BaseAgent):
    name = "scoring"

    async def run(self, analysis: AnalysisBundle) -> dict[str, Any]:  # type: ignore[override]
        user = PROMPT_10_SCORING.format(
            problem_pmf_output=json.dumps(analysis.problem_pmf, default=str),
            business_model_output=json.dumps(analysis.business_model, default=str),
            gtm_team_output=json.dumps(analysis.gtm_team, default=str),
            risk_moat_output=json.dumps(analysis.risk_moat, default=str),
        )
        return await self.llm.chat_json(system=PROMPT_0_SYSTEM, user=user, agent=self.name)
