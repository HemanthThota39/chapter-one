from __future__ import annotations

import json
from typing import Any

from app.core.charts import substitute_charts
from app.core.mermaid_sanitizer import sanitize_markdown
from app.observability import get_logger
from app.pipeline.agents.base import BaseAgent
from app.pipeline.context import FullBundle
from app.prompts.library import PROMPT_0_SYSTEM, PROMPT_11_REPORT


class ReportCompilerAgent(BaseAgent):
    name = "report_compiler"

    async def run(self, bundle: FullBundle) -> dict[str, Any]:  # type: ignore[override]
        research = bundle.analysis.research
        user = PROMPT_11_REPORT.format(
            orchestrator_output=json.dumps(research.orchestrator, default=str),
            market_research_output=json.dumps(research.market, default=str),
            competitor_research_output=json.dumps(research.competitors, default=str),
            timing_research_output=json.dumps(research.timing, default=str),
            regulatory_research_output=json.dumps(research.regulatory, default=str),
            problem_pmf_output=json.dumps(bundle.analysis.problem_pmf, default=str),
            business_model_output=json.dumps(bundle.analysis.business_model, default=str),
            gtm_team_output=json.dumps(bundle.analysis.gtm_team, default=str),
            risk_moat_output=json.dumps(bundle.analysis.risk_moat, default=str),
            scoring_output=json.dumps(bundle.scoring, default=str),
        )
        markdown = await self.llm.chat_text(
            system=PROMPT_0_SYSTEM + "\n\nReturn only the markdown report — no JSON, no preamble.",
            user=user,
            agent=self.name,
        )

        # 1. Substitute chart placeholders with deterministic server-side SVGs
        chart_data = {
            "orchestrator": research.orchestrator,
            "market": research.market,
            "competitors": research.competitors,
            "timing": research.timing,
            "regulatory": research.regulatory,
            "scoring": bundle.scoring,
            "risk_moat": bundle.analysis.risk_moat,
        }
        with_charts, rendered = substitute_charts(markdown, chart_data)
        logger = get_logger()
        if logger:
            logger.event(
                "chart.rendered",
                charts=rendered,
                count=len(rendered),
            )

        # 2. Defense in depth: sanitize any residual Mermaid blocks (shouldn't exist now)
        sanitized = sanitize_markdown(with_charts)

        return {
            "markdown": sanitized.output,
            "charts_rendered": rendered,
            "mermaid_fixes": sanitized.fixes,
        }
