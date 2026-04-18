"""Extract structured signals from OpenAI SDK response objects.

Works with both Chat Completions and Responses API shapes. Handles
SDK-version skew defensively — any missing attribute just produces
a conservative default (empty list / 0).
"""

from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlparse


def _iter(seq: Any) -> Iterable[Any]:
    return seq if isinstance(seq, (list, tuple)) else ()


def _gattr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def extract_usage(resp: Any) -> dict[str, int]:
    """Return {input_tokens, output_tokens} from either API shape."""
    usage = _gattr(resp, "usage")
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    # Chat Completions uses prompt_tokens/completion_tokens.
    # Responses API uses input_tokens/output_tokens.
    input_tok = _gattr(usage, "input_tokens") or _gattr(usage, "prompt_tokens") or 0
    output_tok = _gattr(usage, "output_tokens") or _gattr(usage, "completion_tokens") or 0
    return {"input_tokens": int(input_tok), "output_tokens": int(output_tok)}


def extract_finish_reason(resp: Any) -> str | None:
    """Chat Completions: choices[0].finish_reason. Responses API: status."""
    choices = _gattr(resp, "choices")
    if choices and len(choices) > 0:
        return _gattr(choices[0], "finish_reason")
    return _gattr(resp, "status")


def extract_web_search_signals(resp: Any) -> dict[str, Any]:
    """Pull web_search tool_calls + cited URLs from a Responses API response.

    Returns a dict with:
      - tool_call_count: number of web_search_call items
      - queries: list of queries the model issued
      - urls: sorted unique URLs cited
      - unique_domains: count of distinct hostnames
    """
    tool_call_count = 0
    queries: list[str] = []
    urls: set[str] = set()

    output_items = _gattr(resp, "output") or []
    for item in _iter(output_items):
        item_type = _gattr(item, "type")
        if item_type in {"web_search_call", "web_search_preview_call"}:
            tool_call_count += 1
            # Query lives in different places across SDK versions.
            action = _gattr(item, "action") or _gattr(item, "tool") or {}
            q = _gattr(action, "query") or _gattr(item, "query")
            if q:
                queries.append(str(q))
        # Extract url_citation annotations from message content.
        content = _gattr(item, "content") or []
        for c in _iter(content):
            annotations = _gattr(c, "annotations") or []
            for ann in _iter(annotations):
                if _gattr(ann, "type") in {"url_citation", "citation"}:
                    url = _gattr(ann, "url")
                    if url:
                        urls.add(str(url))

    unique_domains = {urlparse(u).netloc for u in urls if urlparse(u).netloc}
    return {
        "tool_call_count": tool_call_count,
        "queries": queries,
        "urls": sorted(urls),
        "unique_domains": len(unique_domains),
        "citation_count": len(urls),
    }


def scan_parsed_for_urls(parsed: Any) -> list[str]:
    """Walk a parsed JSON dict/list and collect any source_url-like values."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and k.endswith("_url") and v.startswith("http"):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(parsed)
    return list(dict.fromkeys(found))  # dedupe, preserve order


_YEAR_IN_URL = __import__("re").compile(r"/(20\d{2})[-/_]")
_YEAR_ANYWHERE = __import__("re").compile(r"\b(20\d{2})\b")


def year_distribution(urls_or_findings: list[Any]) -> dict[str, Any]:
    """Extract year buckets (fresh/recent/older/unknown) from URLs or findings.

    - fresh: within last 12 months (assumes current year from env or 2026)
    - recent: 12-24 months
    - older: 24+ months
    - unknown: no year extractable
    """
    import datetime

    current_year = datetime.datetime.now(datetime.timezone.utc).year
    buckets = {"fresh": 0, "recent": 0, "older": 0, "unknown": 0}
    years: list[int] = []
    for item in urls_or_findings:
        year: int | None = None
        if isinstance(item, dict):
            # Look for explicit date/year fields first
            for key in ("year", "date", "published_date"):
                val = item.get(key)
                if isinstance(val, (int, str)):
                    m = _YEAR_ANYWHERE.search(str(val))
                    if m:
                        year = int(m.group(1))
                        break
            if year is None:
                url = item.get("source_url") or item.get("url") or ""
                m = _YEAR_IN_URL.search(str(url))
                if m:
                    year = int(m.group(1))
        elif isinstance(item, str):
            m = _YEAR_IN_URL.search(item) or _YEAR_ANYWHERE.search(item)
            if m:
                year = int(m.group(1))

        if year is None:
            buckets["unknown"] += 1
        else:
            years.append(year)
            age = current_year - year
            if age <= 1:
                buckets["fresh"] += 1
            elif age <= 2:
                buckets["recent"] += 1
            else:
                buckets["older"] += 1

    return {
        "distribution": buckets,
        "avg_year": (sum(years) / len(years)) if years else None,
        "min_year": min(years) if years else None,
        "max_year": max(years) if years else None,
        "sample_size": len(years),
    }


def hallucination_signals(parsed: Any) -> dict[str, Any]:
    """Heuristic signals that the agent may have fabricated content.

    - missing_source_urls_count: claims likely to need sources but lack them
    - data_quality_warning_present: was the explicit warning field populated?
    - confidence_distribution: counts of high/medium/low across nested blocks
    """
    warnings_present = False
    confidences = {"high": 0, "medium": 0, "low": 0}
    claims_without_sources = 0

    def walk(node: Any, path: str = "") -> None:
        nonlocal warnings_present, claims_without_sources
        if isinstance(node, dict):
            if str(node.get("data_quality_warning") or "").strip():
                warnings_present = True
            conf = node.get("confidence")
            if isinstance(conf, str) and conf.lower() in confidences:
                confidences[conf.lower()] += 1
            # Heuristic: if a dict mentions a company/figure and has no source_url -> suspect
            has_source = any(
                isinstance(v, str) and v.startswith("http")
                for k, v in node.items()
                if k.endswith("_url") or k == "source_url"
            )
            figure_keys = {"value_usd", "funding_total_usd", "rate_percent", "amount"}
            has_figure = any(k in node for k in figure_keys) or (
                "name" in node and ("founded" in node or "funding_stage" in node)
            )
            if has_figure and not has_source:
                claims_without_sources += 1
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(parsed)
    return {
        "data_quality_warning_present": warnings_present,
        "confidence_distribution": confidences,
        "claims_without_sources": claims_without_sources,
    }
