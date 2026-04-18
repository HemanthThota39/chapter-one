"""Azure OpenAI wrapper.

Two call paths:
  - chat_json(): Chat Completions with strict JSON output, for analysis/scoring/compile.
  - research_json(): Responses API with native web_search tool, for research agents.

Both target the same Azure AI Foundry resource; deployment can differ via env.
Observability: emits structured events via the bound AnalysisLogger.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncAzureOpenAI,
    BadRequestError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.observability import get_logger
from app.observability.extractors import (
    extract_finish_reason,
    extract_usage,
    extract_web_search_signals,
    hallucination_signals,
    scan_parsed_for_urls,
    year_distribution,
)

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = AsyncAzureOpenAI(
            api_key=self.settings.azure_openai_api_key,
            api_version=self.settings.azure_openai_api_version,
            azure_endpoint=self.settings.azure_openai_endpoint,
        )

    @property
    def chat_model(self) -> str:
        return self.settings.azure_openai_deployment

    @property
    def search_model(self) -> str:
        return self.settings.search_deployment

    async def close(self) -> None:
        await self._client.close()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type(
            (APIConnectionError, APITimeoutError, RateLimitError)
        ),
    )
    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        agent: str = "unknown",
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Chat Completions with JSON output for analysis agents."""
        logger = get_logger()
        started = time.perf_counter()

        if logger:
            logger.event(
                "llm.request",
                agent=agent,
                api="chat.completions",
                model=self.chat_model,
                system_chars=len(system),
                user_chars=len(user),
                has_schema=schema is not None,
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {
            "model": self.chat_model,
            "messages": messages,
        }
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.get("title", "Output"),
                    "schema": schema,
                    "strict": True,
                },
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or "{}"
        parsed = _loads_lenient(content)

        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = extract_usage(resp)
        if logger:
            logger.event(
                "llm.response",
                agent=agent,
                api="chat.completions",
                duration_ms=duration_ms,
                finish_reason=extract_finish_reason(resp),
                response_chars=len(content),
                **usage,
            )
            _emit_hallucination_and_citations(logger, agent, parsed, citations=None)
            logger.save_raw(agent, parsed)

        return parsed

    async def chat_text(
        self,
        *,
        system: str,
        user: str,
        agent: str = "unknown",
    ) -> str:
        """Chat Completions returning raw text — used by the report compiler."""
        logger = get_logger()
        started = time.perf_counter()

        if logger:
            logger.event(
                "llm.request",
                agent=agent,
                api="chat.completions.text",
                model=self.chat_model,
                system_chars=len(system),
                user_chars=len(user),
            )

        resp = await self._client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""

        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = extract_usage(resp)
        if logger:
            logger.event(
                "llm.response",
                agent=agent,
                api="chat.completions.text",
                duration_ms=duration_ms,
                finish_reason=extract_finish_reason(resp),
                response_chars=len(text),
                **usage,
            )
            logger.save_raw(agent, {"markdown": text})

        return text

    async def research_json(
        self,
        *,
        system: str,
        user: str,
        agent: str = "unknown",
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Responses API with web_search tool for research agents."""
        logger = get_logger()
        started = time.perf_counter()

        if logger:
            logger.event(
                "llm.request",
                agent=agent,
                api="responses",
                model=self.search_model,
                system_chars=len(system),
                user_chars=len(user),
                has_schema=schema is not None,
            )

        tools: list[dict[str, Any]] = [{"type": "web_search"}]
        kwargs: dict[str, Any] = {
            "model": self.search_model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": tools,
        }
        if schema is not None:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema.get("title", "Output"),
                    "schema": schema,
                    "strict": True,
                }
            }

        try:
            resp = await self._client.responses.create(**kwargs)
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
            resp = await self._client.responses.create(**kwargs)

        text = _extract_response_text(resp)
        parsed = _loads_lenient(text)

        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = extract_usage(resp)
        citations = extract_web_search_signals(resp)
        if logger:
            logger.event(
                "llm.response",
                agent=agent,
                api="responses",
                duration_ms=duration_ms,
                finish_reason=extract_finish_reason(resp),
                response_chars=len(text),
                **usage,
            )
            _emit_hallucination_and_citations(logger, agent, parsed, citations)
            logger.save_raw(agent, parsed)

        return parsed


def _emit_hallucination_and_citations(
    logger: Any,
    agent: str,
    parsed: dict[str, Any],
    citations: dict[str, Any] | None,
) -> None:
    """Emit research.tool_calls, research.citations, research.quality events.

    Citation bug fix: union annotation-URLs with URLs found in the parsed
    JSON payload (source_url fields etc.). The prior version only fell back
    to scanning when annotations were empty, which dropped 4-5 URLs per run.
    """
    if citations is not None:
        logger.event(
            "research.tool_calls",
            agent=agent,
            tool_call_count=citations.get("tool_call_count", 0),
            queries=citations.get("queries", [])[:20],
        )
        annotation_urls = set(citations.get("urls") or [])
        parsed_urls = set(scan_parsed_for_urls(parsed))
        all_urls = sorted(annotation_urls | parsed_urls)
        unique_domains = len({_domain(u) for u in all_urls if _domain(u)})
        freshness = year_distribution(all_urls)
        logger.event(
            "research.citations",
            agent=agent,
            urls=all_urls[:50],
            citation_count=len(all_urls),
            unique_domains=unique_domains,
            annotation_url_count=len(annotation_urls),
            parsed_url_count=len(parsed_urls),
            freshness=freshness,
        )
        if freshness["distribution"]["older"] > freshness["distribution"]["fresh"]:
            logger.event(
                "research.staleness_warning",
                agent=agent,
                distribution=freshness["distribution"],
                avg_year=freshness["avg_year"],
            )
    # Always emit quality/hallucination signals.
    signals = hallucination_signals(parsed)
    logger.event("research.quality", agent=agent, **signals)


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc
    except Exception:  # noqa: BLE001
        return ""


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
            return json.loads(stripped[start : end + 1])
        raise
