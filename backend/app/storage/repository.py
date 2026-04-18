from __future__ import annotations

import json
from typing import Any

from app.pipeline.pipeline import PipelineResult
from app.storage.db import get_pool


class AnalysisRepository:
    async def save(self, result: PipelineResult) -> None:
        pool = await get_pool()
        scoring = result.scoring or {}
        overall_100 = scoring.get("overall_score_100")
        verdict = scoring.get("verdict")
        title = result.orchestrator.get("idea_title") if result.orchestrator else None
        confidence = _derive_confidence(result)

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO analysis_reports
                      (id, idea_text, idea_title, overall_score_100, verdict,
                       confidence, markdown)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    result.analysis_id,
                    result.idea_text,
                    title,
                    overall_100,
                    verdict,
                    confidence,
                    result.markdown,
                )
                for name, payload in _agent_payloads(result).items():
                    await conn.execute(
                        """
                        INSERT INTO agent_outputs (analysis_id, agent_name, output_json)
                        VALUES ($1, $2, $3::jsonb)
                        """,
                        result.analysis_id,
                        name,
                        json.dumps(payload, default=str),
                    )

    async def get_markdown(self, analysis_id: str) -> str | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT markdown FROM analysis_reports WHERE id = $1", analysis_id
            )
            return row["markdown"] if row else None

    async def get_meta(self, analysis_id: str) -> dict[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, idea_text, idea_title, overall_score_100, verdict,
                       confidence, created_at
                FROM analysis_reports WHERE id = $1
                """,
                analysis_id,
            )
            return dict(row) if row else None


def _agent_payloads(result: PipelineResult) -> dict[str, Any]:
    a = result.analysis
    r = a.research
    return {
        "orchestrator": r.orchestrator,
        "market_sizing": r.market,
        "competitive_intel": r.competitors,
        "news_trends": r.timing,
        "regulatory": r.regulatory,
        "problem_pmf": a.problem_pmf,
        "business_model": a.business_model,
        "gtm_team": a.gtm_team,
        "risk_moat": a.risk_moat,
        "scoring": result.scoring,
    }


def _derive_confidence(result: PipelineResult) -> str:
    """Average per-agent confidence -> overall watermark."""
    values: list[int] = []
    mapping = {"high": 1.0, "medium": 0.5, "low": 0.0}
    a = result.analysis
    for block in (a.problem_pmf, a.business_model, a.gtm_team, a.risk_moat):
        if not isinstance(block, dict):
            continue
        for v in block.values():
            if isinstance(v, dict):
                c = v.get("confidence")
                if isinstance(c, str) and c in mapping:
                    values.append(int(mapping[c] * 100))
    if not values:
        return "LOW"
    avg = sum(values) / len(values) / 100
    if avg >= 0.7:
        return "HIGH"
    if avg >= 0.4:
        return "MEDIUM"
    return "LOW"
