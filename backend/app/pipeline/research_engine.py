"""Multi-query research engine — one LLM call per planned query + synthesis.

Previous approach: one Responses API call per research agent, model collapses
3-4 planned queries into 1 tool call → thin citation coverage.

This approach:
  1. For each planned query, fire a DEDICATED responses.create call with web_search.
     The prompt is narrow — "research ONLY this query, return structured findings".
  2. Collect per-query results (URLs + facts + snippets).
  3. One final synthesis call that consumes all per-query outputs + the agent-specific
     template, and emits the agent's structured JSON.

Guarantees one tool call per planned query, dramatic citation growth,
and fine-grained per-query telemetry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.llm import LLMClient
from app.core.progress import bus as progress_bus
from app.observability import get_logger
from app.observability.extractors import (
    extract_finish_reason,
    extract_usage,
    extract_web_search_signals,
    scan_parsed_for_urls,
    year_distribution,
)
from app.prompts.library import PROMPT_0_SYSTEM

log = logging.getLogger(__name__)


PER_QUERY_SYSTEM = (
    PROMPT_0_SYSTEM
    + "\n\nYou are a focused research sub-agent. Your only job is to deeply research "
    "ONE query using the web_search tool. "
    "Freshness matters: prefer sources from 2025 and 2026. Discard sources older "
    "than 2023 unless they are foundational (a law text, a long-standing market "
    "report). When you include an older source, note why it is still authoritative. "
    "Prefer primary sources (company pages, government portals, SEC/Crunchbase, "
    "research firm reports) over secondary blogs or listicles."
)


PER_QUERY_INSTRUCTION = """Research this query thoroughly using the web_search tool.

Return a JSON object with this exact shape:
{{
  "query": "<echo the query>",
  "findings": [
    {{
      "fact": "<one concrete fact, figure, or claim — no prose>",
      "source_url": "<URL the fact came from>",
      "publisher": "<site or organisation name>",
      "date": "<YYYY or YYYY-MM-DD if known; leave empty if unknown>",
      "freshness": "fresh | recent | older"
    }}
  ],
  "notes": "<caveats, conflicts between sources, or gaps you noticed>"
}}

`freshness` values: "fresh" (last 12 months), "recent" (12-24 months), "older" (>24 months).

Rules:
- Call the web_search tool AT LEAST TWICE for this query — the first with the query
  verbatim, the second with a reformulation to expand coverage.
- If after two searches you still have fewer than 5 findings, search a third time
  with a narrower, more specific reformulation.
- Include every URL you actually cited in findings[].source_url.
- 5-15 high-quality findings per query. More if the topic is rich. Reject weak/tangential findings.
- Each finding must be a SINGLE fact, not a paragraph. Split multi-fact findings into rows.
- Do NOT synthesise across queries — answer ONLY the given query.
- Do NOT invent URLs or dates; leave empty if unknown.

Query to research: {query}

Context (for disambiguation only — do NOT treat as findings):
{context}"""


@dataclass
class QueryResult:
    query: str
    agent: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    duration_ms: int = 0
    tool_call_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def citation_count(self) -> int:
        return len(self.urls)

    def summarise_for_synthesis(self) -> dict[str, Any]:
        """Trimmed form passed to the synthesis step."""
        return {
            "query": self.query,
            "findings": self.findings[:30],  # cap per-query findings for token sanity
            "citations": self.urls,
        }


class ResearchEngine:
    def __init__(self, llm: LLMClient, concurrency: int = 4) -> None:
        self.llm = llm
        self._sem = asyncio.Semaphore(concurrency)

    async def run(
        self,
        *,
        agent: str,
        queries: list[str],
        context: dict[str, Any],
        synthesis_prompt: str,
    ) -> dict[str, Any]:
        """Fire per-query research, then synthesise into the agent's output schema."""
        logger = get_logger()
        if logger:
            logger.event(
                "research.plan",
                agent=agent,
                planned_queries=queries,
                planned_count=len(queries),
                concurrency=self._sem._value,  # noqa: SLF001
            )

        if not queries:
            log.warning("%s: no planned queries — returning empty result", agent)
            return await self._synthesise(agent, [], synthesis_prompt)

        # Fire per-query calls in parallel (bounded by semaphore)
        tasks = [
            asyncio.create_task(self._fire_query(agent, q, context))
            for q in queries
        ]
        query_results: list[QueryResult] = await asyncio.gather(*tasks)

        # Coverage check — emit warning if model ran fewer tool calls than expected
        actual_tool_calls = sum(r.tool_call_count for r in query_results)
        successful = sum(1 for r in query_results if r.error is None)
        if logger:
            logger.event(
                "research.coverage",
                agent=agent,
                planned_queries=len(queries),
                successful_queries=successful,
                failed_queries=len(queries) - successful,
                total_tool_calls=actual_tool_calls,
                total_urls=sum(r.citation_count for r in query_results),
            )
            if successful < max(1, int(len(queries) * 0.75)):
                logger.event(
                    "research.coverage_warning",
                    agent=agent,
                    reason="fewer_than_75_percent_queries_succeeded",
                    planned=len(queries),
                    successful=successful,
                )

            # Aggregated research.citations — union of all per-query URLs so that
            # summary.md + metrics pick them up. (Bug fix: previously no
            # research.citations events were emitted under the multi-query flow.)
            all_urls: set[str] = set()
            for r in query_results:
                all_urls.update(r.urls)
            sorted_urls = sorted(all_urls)
            unique_domains = len({urlparse(u).netloc for u in sorted_urls if urlparse(u).netloc})
            freshness = year_distribution(sorted_urls)
            logger.event(
                "research.citations",
                agent=agent,
                urls=sorted_urls[:80],
                citation_count=len(sorted_urls),
                unique_domains=unique_domains,
                freshness=freshness,
                aggregated_from="per_query",
            )
            if freshness["distribution"]["older"] > freshness["distribution"]["fresh"]:
                logger.event(
                    "research.staleness_warning",
                    agent=agent,
                    distribution=freshness["distribution"],
                    avg_year=freshness["avg_year"],
                )

        return await self._synthesise(agent, query_results, synthesis_prompt)

    async def _fire_query(
        self, agent: str, query: str, context: dict[str, Any]
    ) -> QueryResult:
        logger = get_logger()
        started = time.perf_counter()
        async with self._sem:
            if logger:
                logger.event("research.query_start", agent=agent, query=query)
                aid = logger.analysis_id
                # Best-effort SSE sub-step update; never fails the query.
                try:
                    await progress_bus.publish_detail(
                        aid, f"[{agent}] searching: {query[:90]}"
                    )
                except Exception:  # noqa: BLE001
                    pass
            try:
                ctx_blob = json.dumps(
                    {
                        "idea_title": context.get("idea_title", ""),
                        "industry": context.get("industry", ""),
                        "sub_sector": context.get("sub_sector", ""),
                        "geography_focus": context.get("geography_focus", ""),
                        "target_customer": context.get("target_customer", {}),
                    },
                    indent=2,
                )
                user_prompt = PER_QUERY_INSTRUCTION.format(query=query, context=ctx_blob)
                parsed, meta = await self._responses_with_search_retrying(
                    agent=f"{agent}::query", system=PER_QUERY_SYSTEM, user=user_prompt
                )
            except Exception as e:  # noqa: BLE001
                duration_ms = int((time.perf_counter() - started) * 1000)
                log.exception("research.query failed: agent=%s query=%s", agent, query)
                if logger:
                    logger.event(
                        "research.query_error",
                        agent=agent,
                        query=query,
                        duration_ms=duration_ms,
                        error_type=type(e).__name__,
                        message=str(e)[:500],
                    )
                return QueryResult(query=query, agent=agent, error=str(e))

        duration_ms = int((time.perf_counter() - started) * 1000)
        findings = parsed.get("findings") if isinstance(parsed, dict) else []
        findings = findings if isinstance(findings, list) else []

        # Extract URLs — union annotation URLs with any URLs in findings
        annotation_urls = set(meta.get("urls") or [])
        finding_urls = {
            f.get("source_url")
            for f in findings
            if isinstance(f, dict) and isinstance(f.get("source_url"), str)
            and f.get("source_url", "").startswith("http")
        }
        all_urls = sorted(annotation_urls | finding_urls)

        result = QueryResult(
            query=query,
            agent=agent,
            findings=findings,
            urls=all_urls,
            duration_ms=duration_ms,
            tool_call_count=meta.get("tool_call_count", 0),
            raw=parsed if isinstance(parsed, dict) else {},
        )

        if logger:
            logger.event(
                "research.query_fired",
                agent=agent,
                query=query,
                duration_ms=duration_ms,
                tool_call_count=result.tool_call_count,
                finding_count=len(findings),
                citation_count=len(all_urls),
                urls=all_urls[:30],
            )
            try:
                await progress_bus.publish_detail(
                    logger.analysis_id,
                    f"[{agent}] ✓ {len(findings)} findings, {len(all_urls)} URLs from: {query[:70]}",
                )
            except Exception:  # noqa: BLE001
                pass
        return result

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=3, max=40),
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError)
        ),
    )
    async def _responses_with_search_retrying(
        self, *, agent: str, system: str, user: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Retry wrapper — bumped to 4 attempts with longer backoff since
        web_search at high concurrency hits Azure's TPM ceiling frequently."""
        return await self._responses_with_search(agent=agent, system=system, user=user)

    async def _responses_with_search(
        self, *, agent: str, system: str, user: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Low-level Responses API call with web_search enabled.

        Bypasses LLMClient.research_json because we want per-query telemetry
        without the synthesised hallucination/citations events (those are
        for the final synthesis step).
        """
        logger = get_logger()
        client = self.llm._client  # noqa: SLF001
        model = self.llm.search_model

        kwargs: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [{"type": "web_search"}],
        }

        from openai import BadRequestError

        try:
            resp = await client.responses.create(**kwargs)
        except BadRequestError as e:
            log.warning("web_search rejected; retrying with web_search_preview: %s", e)
            if logger:
                logger.event(
                    "llm.fallback",
                    agent=agent,
                    from_tool="web_search",
                    to_tool="web_search_preview",
                    reason=str(e)[:200],
                )
            kwargs["tools"] = [{"type": "web_search_preview"}]
            resp = await client.responses.create(**kwargs)

        text = _extract_response_text(resp)
        parsed = _loads_lenient(text)

        usage = extract_usage(resp)
        meta = extract_web_search_signals(resp)
        # Enrich with any url-keyed fields in the parsed JSON
        scanned = set(scan_parsed_for_urls(parsed))
        meta_urls = set(meta.get("urls", []) or [])
        meta["urls"] = sorted(meta_urls | scanned)
        meta["citation_count"] = len(meta["urls"])
        if logger:
            logger.event(
                "llm.response",
                agent=agent,
                api="responses",
                duration_ms=0,  # captured by caller
                finish_reason=extract_finish_reason(resp),
                response_chars=len(text),
                **usage,
            )
        return (parsed if isinstance(parsed, dict) else {}, meta)

    async def _synthesise(
        self,
        agent: str,
        query_results: list[QueryResult],
        synthesis_prompt: str,
    ) -> dict[str, Any]:
        """Final call that folds all per-query findings into the agent's schema."""
        logger = get_logger()
        successful = [r for r in query_results if r.error is None]
        findings_blob = json.dumps(
            [r.summarise_for_synthesis() for r in successful],
            indent=2,
            default=str,
        )

        if logger:
            logger.event(
                "research.synthesis_start",
                agent=agent,
                queries_used=len(successful),
                total_findings=sum(len(r.findings) for r in successful),
                total_citations=sum(r.citation_count for r in successful),
                findings_chars=len(findings_blob),
            )

        user = (
            synthesis_prompt
            + "\n\nRESEARCH FINDINGS (from per-query sub-agents — every source_url is verified):\n"
            + findings_blob
            + "\n\nSynthesise the findings above into the JSON schema described earlier. "
            "Carry every relevant source_url forward into your output. "
            "Do NOT introduce facts not present in the findings. "
            "If findings conflict, pick the most recent + most authoritative source "
            "and note the conflict in the notes/data_quality_warning field."
        )

        parsed = await self.llm.chat_json(
            system=PROMPT_0_SYSTEM,
            user=user,
            agent=f"{agent}::synthesis",
        )

        if logger:
            logger.event(
                "research.synthesis_complete",
                agent=agent,
                response_keys=list(parsed.keys()) if isinstance(parsed, dict) else [],
            )
        return parsed


def _extract_response_text(resp: Any) -> str:
    if getattr(resp, "output_text", None):
        return resp.output_text
    output = getattr(resp, "output", None) or []
    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for c in content:
            text = getattr(c, "text", None)
            if text:
                parts.append(text if isinstance(text, str) else getattr(text, "value", ""))
    return "".join(parts)


def _loads_lenient(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json\n"):
            stripped = stripped[5:]
        stripped = stripped.rstrip("`").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {"parse_error": True, "raw": stripped[:2000]}
