"""Aggregate metrics across events.jsonl files.

Usage:
  python -m app.observability.metrics              # summary across all analyses
  python -m app.observability.metrics <analysis_id>  # detail for one run
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def per_analysis_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    starts = {e["agent"]: e for e in events if e["event"] == "agent.start"}
    completes = {e["agent"]: e for e in events if e["event"] == "agent.complete"}
    errors = [e for e in events if e["event"] == "agent.error"]
    llm_calls = [e for e in events if e["event"] == "llm.response"]
    citations = [e for e in events if e["event"] == "research.citations"]
    tool_calls = [e for e in events if e["event"] == "research.tool_calls"]
    hallucination = [e for e in events if e["event"] == "research.quality"]
    query_fired = [e for e in events if e["event"] == "research.query_fired"]
    query_errors = [e for e in events if e["event"] == "research.query_error"]
    coverage = [e for e in events if e["event"] == "research.coverage"]
    staleness = [e for e in events if e["event"] == "research.staleness_warning"]
    sanitizer_events = [e for e in events if e["event"] == "chart.sanitizer_applied"]
    pipeline_done = next(
        (e for e in events if e["event"] == "pipeline.complete"), None
    )
    render_errors = [e for e in events if e["event"] == "render.mermaid_error"]

    total_tokens_in = sum(int(e.get("input_tokens", 0)) for e in llm_calls)
    total_tokens_out = sum(int(e.get("output_tokens", 0)) for e in llm_calls)

    durations_by_agent = {
        e["agent"]: int(e.get("duration_ms", 0)) for e in completes.values()
    }

    total_urls = sum(len(e.get("urls", [])) for e in citations)
    total_domains = sum(int(e.get("unique_domains", 0)) for e in citations)
    total_tool_calls = sum(int(e.get("tool_call_count", 0)) for e in tool_calls)

    halluc = {
        "data_quality_warnings": sum(
            1 for e in hallucination if e.get("data_quality_warning_present")
        ),
        "claims_without_sources_total": sum(
            int(e.get("claims_without_sources", 0)) for e in hallucination
        ),
        "confidence_low_total": sum(
            int(e.get("confidence_distribution", {}).get("low", 0))
            for e in hallucination
        ),
    }

    # Research depth — new fields from the multi-query engine
    per_query_tool_calls = sum(int(e.get("tool_call_count", 0)) for e in query_fired)
    per_query_citations = sum(int(e.get("citation_count", 0)) for e in query_fired)
    total_chart_fixes = sum(int(e.get("total_fixes", 0)) for e in sanitizer_events)

    return {
        "agents_started": len(starts),
        "agents_completed": len(completes),
        "agents_errored": [e["agent"] for e in errors],
        "durations_by_agent_ms": durations_by_agent,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_urls_cited": total_urls,
        "total_unique_domains": total_domains,
        "total_web_searches": total_tool_calls + per_query_tool_calls,
        "queries_fired_count": len(query_fired),
        "queries_failed_count": len(query_errors),
        "per_query_citations": per_query_citations,
        "staleness_warnings": len(staleness),
        "chart_sanitizer_fixes": total_chart_fixes,
        "coverage_events": len(coverage),
        "hallucination": halluc,
        "render_errors": len(render_errors),
        "pipeline": pipeline_done or {},
    }


def aggregate_across_analyses(log_dir: Path) -> dict[str, Any]:
    """Summary stats across every analysis folder under log_dir."""
    analyses = []
    for sub in sorted(log_dir.iterdir()):
        if not sub.is_dir():
            continue
        events = read_events(sub / "events.jsonl")
        if not events:
            continue
        analyses.append({"id": sub.name, "stats": per_analysis_stats(events)})

    if not analyses:
        return {"count": 0}

    agent_latencies: dict[str, list[int]] = {}
    error_counts: dict[str, int] = {}
    total_tokens_in = 0
    total_tokens_out = 0
    total_urls = 0
    total_warnings = 0

    for a in analyses:
        s = a["stats"]
        for agent, ms in s.get("durations_by_agent_ms", {}).items():
            agent_latencies.setdefault(agent, []).append(ms)
        for agent in s.get("agents_errored", []):
            error_counts[agent] = error_counts.get(agent, 0) + 1
        total_tokens_in += s.get("total_tokens_in", 0)
        total_tokens_out += s.get("total_tokens_out", 0)
        total_urls += s.get("total_urls_cited", 0)
        total_warnings += s.get("hallucination", {}).get("data_quality_warnings", 0)

    p = {
        agent: {
            "p50_ms": int(median(lats)),
            "avg_ms": int(mean(lats)),
            "max_ms": max(lats),
            "n": len(lats),
        }
        for agent, lats in agent_latencies.items()
    }

    return {
        "count": len(analyses),
        "latency_by_agent": p,
        "error_counts_by_agent": error_counts,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "avg_urls_per_run": round(total_urls / len(analyses), 1),
        "total_quality_warnings": total_warnings,
    }


def _print_table(title: str, data: dict[str, Any]) -> None:
    print(f"\n== {title} ==")
    for k, v in data.items():
        print(f"  {k:32s} {v}")


def main() -> None:
    log_dir = Path("logs")
    if len(sys.argv) > 1:
        aid = sys.argv[1]
        events = read_events(log_dir / aid / "events.jsonl")
        stats = per_analysis_stats(events)
        _print_table(f"Analysis {aid}", stats)
        return
    agg = aggregate_across_analyses(log_dir)
    _print_table(f"Aggregate across {agg.get('count', 0)} analyses", agg)


if __name__ == "__main__":
    main()
