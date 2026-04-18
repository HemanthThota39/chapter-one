"""Analysis worker — consumes Service Bus `analyses.submitted`, runs pipeline,
writes progress (analysis_events + NOTIFY), sections, raw agent dumps.

Entrypoint:
  python -m app.workers.analysis_worker

Container Apps Job's KEDA scale rule on the Service Bus queue fires a new
replica per message. Each replica handles one message then exits.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from typing import Any

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver
from azure.servicebus.exceptions import MessageLockLostError

from app.config import get_settings
from app.core.charts import substitute_charts
from app.core.llm import LLMClient
from app.core.mermaid_sanitizer import sanitize_markdown
from app.core.progress import ProgressEvent
from app.db import close_pool, get_pool
from app.observability import AnalysisLogger, bind_logger
from app.pipeline.pipeline import StartupAnalysisPipeline
from app.storage import analyses as store
from app.storage.analyses import SectionInput, next_free_slug, slugify

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


STAGE_LABELS: dict[str, str] = {
    "classifying":  "Classifying idea",
    "research":     "Running parallel research",
    "research_done":"Research complete",
    "analysis_1":   "Analysing problem + business model",
    "analysis_2":   "Analysing GTM + risk",
    "scoring":      "Computing CVF scores",
    "compiling":    "Generating markdown report",
    "done":         "Complete",
    "error":        "Error",
}


async def _one_iteration() -> bool:
    """Pull exactly one message from the queue, process it, ack/dead-letter.
    Returns True if a message was processed, False if the queue was empty."""
    settings = get_settings()
    if not settings.service_bus_namespace:
        raise RuntimeError("SERVICE_BUS_NAMESPACE not configured")

    cred = DefaultAzureCredential()
    async with ServiceBusClient(
        fully_qualified_namespace=settings.service_bus_namespace,
        credential=cred,
    ) as sb:
        async with sb.get_queue_receiver(settings.service_bus_queue_analyses, max_wait_time=5) as receiver:
            msgs = await receiver.receive_messages(max_message_count=1, max_wait_time=10)
            if not msgs:
                return False
            msg = msgs[0]
            try:
                payload = json.loads(str(msg))
                analysis_id = payload["analysis_id"]
                log.info("Processing analysis %s", analysis_id)
                await _process_one(analysis_id, receiver, msg)
                await receiver.complete_message(msg)
                log.info("Completed %s", analysis_id)
            except MessageLockLostError:
                log.warning("Lock lost; message will be re-delivered")
            except Exception:  # noqa: BLE001
                log.exception("Failed to process message — sending to DLQ after retries exhausted")
                try:
                    await receiver.abandon_message(msg)
                except Exception:  # noqa: BLE001
                    pass
    return True


async def _process_one(
    analysis_id: str, receiver: ServiceBusReceiver, sb_msg: Any,
) -> None:
    # 1) Load analysis
    row = await store.get_analysis(analysis_id)
    if row is None:
        log.warning("Analysis %s missing in DB; dropping message", analysis_id)
        return
    owner_id = str(row["owner_id"])
    idea_text = row["idea_text"]

    await store.mark_running(analysis_id)
    await store.publish_event(analysis_id, kind="progress", stage="classifying", percent=5, message="Starting...")

    # 2) Bind the Phase 1 observability logger to this run (logs to Blob path)
    logger = AnalysisLogger(
        analysis_id=analysis_id,
        log_dir=os.path.join("/tmp", "logs"),  # ephemeral on worker; real observability in App Insights
        log_raw_responses=True,
    )

    llm = LLMClient()
    pipeline = StartupAnalysisPipeline(llm)

    # Monkey-patch the pipeline's bus.publish so it writes to Postgres + NOTIFY
    # instead of the in-memory bus.
    _install_bus_adapter(analysis_id)

    try:
        with bind_logger(logger):
            started = time.perf_counter()
            logger.event("pipeline.start", idea_chars=len(idea_text))
            result = await pipeline._run_inner(analysis_id, idea_text)
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.event("pipeline.complete", duration_ms=duration_ms)
    except Exception as e:
        log.exception("pipeline error\n%s", traceback.format_exc())
        await store.mark_failed(analysis_id, error_message=str(e))
        await store.publish_event(analysis_id, kind="progress", stage="error", percent=100, message=str(e)[:200])
        return

    # 3) Persist per-agent JSON dumps
    research = result.research
    for agent_name, payload in [
        ("orchestrator", research.orchestrator),
        ("market_sizing", research.market),
        ("competitive_intel", research.competitors),
        ("news_trends", research.timing),
        ("regulatory", research.regulatory),
        ("problem_pmf", result.analysis.problem_pmf),
        ("business_model", result.analysis.business_model),
        ("gtm_team", result.analysis.gtm_team),
        ("risk_moat", result.analysis.risk_moat),
        ("scoring", result.scoring),
    ]:
        try:
            await store.save_agent_output(analysis_id, agent_name, payload if isinstance(payload, dict) else {"raw": str(payload)})
        except Exception:  # noqa: BLE001
            log.exception("failed to save raw for %s", agent_name)

    # 4) Build sections from the generated markdown + structured data
    full_markdown = _substitute_charts_and_sanitize(result)
    sections = _split_report_into_sections(full_markdown, result)

    idea_title = (research.orchestrator or {}).get("idea_title") or "Untitled analysis"
    overall_100 = (result.scoring or {}).get("overall_score_100")
    verdict = (result.scoring or {}).get("verdict")
    confidence = _derive_confidence(result)

    # 5) Persist sections + v1 + mark done
    version_id = await store.save_initial_version(
        analysis_id,
        sections,
        overall_score_100=overall_100,
        verdict=verdict,
    )
    slug_base = slugify(idea_title)
    slug = await next_free_slug(owner_id, slug_base)
    await store.mark_done(
        analysis_id,
        idea_title=idea_title,
        overall_score_100=overall_100,
        verdict=verdict,
        confidence=confidence,
        slug=slug,
        current_version_id=version_id,
    )
    # Auto-publish to the global feed when visibility=public
    if row["visibility"] == "public":
        try:
            from app.storage.social import create_post_if_missing
            await create_post_if_missing(analysis_id, owner_id, caption=None)
        except Exception:  # noqa: BLE001
            log.exception("Failed to auto-create post; analysis saved but not in feed")

    await store.publish_event(analysis_id, kind="progress", stage="done", percent=100, message=f"Analysis complete · {verdict} {overall_100}/100")
    # Update user's streak + total
    await _update_user_activity(owner_id)


def _install_bus_adapter(analysis_id: str) -> None:
    """Route the Phase 1 in-memory ProgressBus.publish into Postgres NOTIFY."""
    from app.core import progress as progress_mod

    real_bus = progress_mod.bus

    async def _publish(aid: str, event: ProgressEvent) -> None:
        await store.publish_event(
            aid,
            kind=event.kind,
            stage=event.stage,
            percent=event.percent,
            message=event.message,
        )

    async def _publish_detail(aid: str, message: str, stage: str = "", percent: int = -1) -> None:
        await store.publish_event(aid, kind="detail", stage=stage, percent=percent, message=message)

    async def _noop_close(aid: str) -> None:
        pass

    real_bus.publish = _publish  # type: ignore[assignment]
    real_bus.publish_detail = _publish_detail  # type: ignore[assignment]
    real_bus.close = _noop_close  # type: ignore[assignment]


def _substitute_charts_and_sanitize(result: Any) -> str:
    """Render SVG charts into the LLM-produced markdown, then sanitize."""
    md = result.markdown
    chart_data = {
        "orchestrator": result.research.orchestrator,
        "market": result.research.market,
        "competitors": result.research.competitors,
        "timing": result.research.timing,
        "regulatory": result.research.regulatory,
        "scoring": result.scoring,
        "risk_moat": result.analysis.risk_moat,
    }
    with_charts, _ = substitute_charts(md, chart_data)
    sanitized = sanitize_markdown(with_charts)
    return sanitized.output


def _split_report_into_sections(markdown: str, result: Any) -> list[SectionInput]:
    """Naive section splitter by H2 headings.
    Phase 2 doesn't need perfect section keys yet — we store the whole report
    under 'executive_summary' as a single section and let the renderer
    concatenate. M4 will refactor the compiler to emit proper per-section
    output. For now, this is enough to support persistence + rendering.
    """
    # Keep it simple: one section 'full_report' holding everything. The
    # renderer concatenates section content in order, and this single-section
    # approach round-trips cleanly through report_sections/report_versions.
    return [
        SectionInput(
            section_key="executive_summary",
            content_md=markdown,
            source_agents=["report_compiler"],
            structured_payload={
                "scoring": result.scoring,
                "orchestrator": result.research.orchestrator,
            },
        ),
    ]


def _derive_confidence(result: Any) -> str:
    mapping = {"high": 1.0, "medium": 0.5, "low": 0.0}
    values: list[float] = []
    for block in (result.analysis.problem_pmf, result.analysis.business_model,
                  result.analysis.gtm_team, result.analysis.risk_moat):
        if not isinstance(block, dict):
            continue
        for v in block.values():
            if isinstance(v, dict):
                c = v.get("confidence")
                if isinstance(c, str) and c in mapping:
                    values.append(mapping[c])
    if not values:
        return "LOW"
    avg = sum(values) / len(values)
    return "HIGH" if avg >= 0.7 else ("MEDIUM" if avg >= 0.4 else "LOW")


async def _update_user_activity(owner_id: str) -> None:
    """Increment total_analyses + bump streak if today is a new day."""
    from datetime import date
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_activity_date, current_streak, longest_streak, timezone FROM users WHERE id=$1::uuid",
            owner_id,
        )
        if not row:
            return
        # For MVP, use UTC today; full timezone-aware logic comes in M3
        today = date.today()
        last = row["last_activity_date"]
        if last == today:
            current = row["current_streak"]
        elif last and (today - last).days == 1:
            current = row["current_streak"] + 1
        else:
            current = 1
        longest = max(row["longest_streak"], current)
        await conn.execute(
            """UPDATE users
                  SET total_analyses = total_analyses + 1,
                      current_streak = $2,
                      longest_streak = $3,
                      last_activity_date = $4,
                      updated_at = NOW()
                WHERE id=$1::uuid""",
            owner_id, current, longest, today,
        )


async def main() -> int:
    """Worker loop — KEDA-triggered replicas process one message then exit.

    We try up to 3 queue polls per replica (Azure sometimes delivers with
    some lag). Then exit so the replica scales down.
    """
    for attempt in range(3):
        try:
            got = await _one_iteration()
        except Exception:
            log.exception("Iteration failed")
            got = False
        if got:
            return 0
        await asyncio.sleep(2)
    log.info("No messages after 3 polls — exiting")
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    finally:
        try:
            asyncio.run(close_pool())
        except Exception:
            pass
    sys.exit(rc)
