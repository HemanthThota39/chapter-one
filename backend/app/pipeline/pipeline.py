from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.llm import LLMClient
from app.core.progress import ProgressEvent, bus
from app.observability import AnalysisLogger, bind_logger
from app.observability.summary import build_summary
from app.pipeline.agents.business_model import BusinessModelAgent
from app.pipeline.agents.competitive_intel import CompetitiveIntelAgent
from app.pipeline.agents.gtm_team import GtmTeamAgent
from app.pipeline.agents.market_sizing import MarketSizingAgent
from app.pipeline.agents.news_trends import NewsTrendsAgent
from app.pipeline.agents.orchestrator import OrchestratorAgent
from app.pipeline.agents.problem_pmf import ProblemPmfAgent
from app.pipeline.agents.regulatory import RegulatoryAgent
from app.pipeline.agents.report_compiler import ReportCompilerAgent
from app.pipeline.agents.risk_moat import RiskMoatAgent
from app.pipeline.agents.safety_gate import SafetyGate, SafetyRejected
from app.pipeline.agents.scoring import ScoringAgent
from app.pipeline.context import AnalysisBundle, FullBundle, ResearchBundle
from app.pipeline.research_engine import ResearchEngine

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    analysis_id: str
    idea_text: str
    orchestrator: dict[str, Any]
    research: ResearchBundle
    analysis: AnalysisBundle
    scoring: dict[str, Any]
    markdown: str


class StartupAnalysisPipeline:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.engine = ResearchEngine(
            llm, concurrency=get_settings().research_concurrency
        )
        self.safety_gate = SafetyGate(llm)
        self.orchestrator = OrchestratorAgent(llm)
        self.market = MarketSizingAgent(llm, self.engine)
        self.competitors = CompetitiveIntelAgent(llm, self.engine)
        self.news = NewsTrendsAgent(llm, self.engine)
        self.regulatory = RegulatoryAgent(llm, self.engine)
        self.problem_pmf = ProblemPmfAgent(llm)
        self.business_model = BusinessModelAgent(llm)
        self.gtm_team = GtmTeamAgent(llm)
        self.risk_moat = RiskMoatAgent(llm)
        self.scoring = ScoringAgent(llm)
        self.compiler = ReportCompilerAgent(llm)

    @staticmethod
    def new_analysis_id() -> str:
        return str(uuid.uuid4())

    async def _publish(self, aid: str, stage: str, percent: int, message: str = "") -> None:
        await bus.publish(aid, ProgressEvent(stage=stage, percent=percent, message=message))

    async def run(self, analysis_id: str, idea_text: str) -> PipelineResult:
        settings = get_settings()
        logger = AnalysisLogger(
            analysis_id=analysis_id,
            log_dir=Path(settings.log_dir),
            log_raw_responses=settings.log_raw_responses,
        )
        logger.event(
            "pipeline.start",
            idea_chars=len(idea_text),
            idea_text=idea_text if settings.log_idea_text else None,
            model=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
        )
        started = time.perf_counter()

        with bind_logger(logger):
            try:
                result = await self._run_inner(analysis_id, idea_text)
                duration_ms = int((time.perf_counter() - started) * 1000)
                logger.event(
                    "pipeline.complete",
                    duration_ms=duration_ms,
                    overall_score_100=(result.scoring or {}).get("overall_score_100"),
                    verdict=(result.scoring or {}).get("verdict"),
                )
                return result
            except Exception as e:
                duration_ms = int((time.perf_counter() - started) * 1000)
                logger.event(
                    "pipeline.error",
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                    message=str(e)[:500],
                )
                raise
            finally:
                # Always write the human-readable summary.
                try:
                    summary = build_summary(logger.dir)
                    logger.write_summary(summary)
                except Exception:  # noqa: BLE001
                    log.exception("Failed to build summary.md")

    async def _run_inner(self, analysis_id: str, idea_text: str) -> PipelineResult:
        await self._publish(analysis_id, "classifying", 2, "Validating input...")
        verdict = await self.safety_gate.run(idea_text)
        if not verdict.valid:
            raise SafetyRejected(verdict)

        await self._publish(analysis_id, "classifying", 5, "Classifying idea...")
        metadata = await self.orchestrator.run(idea_text)

        await self._publish(analysis_id, "research", 15, "Running parallel market research...")
        market_t = asyncio.create_task(self.market._safe_run(metadata))
        comp_t = asyncio.create_task(self.competitors._safe_run(metadata))
        news_t = asyncio.create_task(self.news._safe_run(metadata))
        reg_t = asyncio.create_task(self.regulatory._safe_run(metadata))
        market, comp, news, reg = await asyncio.gather(market_t, comp_t, news_t, reg_t)
        await self._publish(analysis_id, "research_done", 45, "Research complete.")

        research = ResearchBundle(
            orchestrator=metadata,
            market=market,
            competitors=comp,
            timing=news,
            regulatory=reg,
        )

        await self._publish(analysis_id, "analysis_1", 50, "Analysing problem + business model...")
        ppmf_t = asyncio.create_task(self.problem_pmf._safe_run(research))
        bm_t = asyncio.create_task(self.business_model._safe_run(research))
        ppmf, bm = await asyncio.gather(ppmf_t, bm_t)

        await self._publish(analysis_id, "analysis_2", 65, "Analysing GTM + risk...")
        gtm_t = asyncio.create_task(self.gtm_team._safe_run(research))
        rm_t = asyncio.create_task(self.risk_moat._safe_run(research))
        gtm, rm = await asyncio.gather(gtm_t, rm_t)

        analysis = AnalysisBundle(
            research=research,
            problem_pmf=ppmf,
            business_model=bm,
            gtm_team=gtm,
            risk_moat=rm,
        )

        await self._publish(analysis_id, "scoring", 80, "Computing CVF scores...")
        scoring = await self.scoring.run(analysis)

        await self._publish(analysis_id, "compiling", 90, "Generating markdown report...")
        compiled = await self.compiler.run(FullBundle(analysis=analysis, scoring=scoring))
        markdown = compiled.get("markdown", "")

        await self._publish(analysis_id, "done", 100, "Analysis complete.")
        return PipelineResult(
            analysis_id=analysis_id,
            idea_text=idea_text,
            orchestrator=metadata,
            research=research,
            analysis=analysis,
            scoring=scoring,
            markdown=markdown,
        )
