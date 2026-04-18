"""Build per-analysis summary.md from events.jsonl."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.metrics import per_analysis_stats, read_events


def build_summary(analysis_dir: Path) -> str:
    events = read_events(analysis_dir / "events.jsonl")
    if not events:
        return f"# Analysis {analysis_dir.name}\n\nNo events logged.\n"

    stats = per_analysis_stats(events)
    pipe_start = next((e for e in events if e["event"] == "pipeline.start"), {})
    pipe_done = stats.get("pipeline", {}) or {}

    start_ts = pipe_start.get("ts")
    start_str = (
        datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(timespec="seconds")
        if start_ts
        else "unknown"
    )
    total_ms = int(pipe_done.get("duration_ms", 0))

    lines: list[str] = []
    lines.append(f"# Analysis {analysis_dir.name}")
    lines.append("")
    lines.append(f"- Started: {start_str}")
    lines.append(f"- Duration: {total_ms/1000:.1f}s")
    lines.append(f"- Idea chars: {pipe_start.get('idea_chars', '?')}")
    verdict = pipe_done.get("verdict", "—")
    score = pipe_done.get("overall_score_100", "—")
    lines.append(f"- Overall: {score}/100 · {verdict}")
    failed = stats.get("agents_errored") or []
    lines.append(f"- Failed agents: {', '.join(failed) if failed else 'none'}")
    lines.append("")

    # Timing + tokens per agent
    lines.append("## Timing & tokens")
    lines.append("")
    lines.append("| Agent | Status | Duration | Tokens (in/out) |")
    lines.append("|---|---|---|---|")
    llm_by_agent = _group_llm_by_agent(events)
    durations = stats.get("durations_by_agent_ms", {})
    all_agents = sorted(set(list(durations.keys()) + failed + list(llm_by_agent.keys())))
    for agent in all_agents:
        status = "✗" if agent in failed else "✓"
        dur = durations.get(agent)
        dur_str = f"{dur/1000:.1f}s" if dur else "—"
        tok = llm_by_agent.get(agent, {"in": 0, "out": 0})
        tok_str = f"{tok['in']} / {tok['out']}" if tok["in"] else "—"
        lines.append(f"| {agent} | {status} | {dur_str} | {tok_str} |")
    lines.append("")

    # Research depth — planned vs fired queries
    lines.append("## Research depth")
    lines.append("")
    plans = {e["agent"]: e for e in events if e["event"] == "research.plan"}
    coverage = {e["agent"]: e for e in events if e["event"] == "research.coverage"}
    if plans or coverage:
        lines.append("| Agent | Planned queries | Fired | Failed | Tool calls | URLs |")
        lines.append("|---|---|---|---|---|---|")
        for agent in sorted(plans.keys() | coverage.keys()):
            p = plans.get(agent, {})
            c = coverage.get(agent, {})
            planned = p.get("planned_count", c.get("planned_queries", 0))
            fired = c.get("successful_queries", "?")
            failed_q = c.get("failed_queries", "?")
            tool = c.get("total_tool_calls", "?")
            urls = c.get("total_urls", "?")
            lines.append(f"| {agent} | {planned} | {fired} | {failed_q} | {tool} | {urls} |")
    else:
        lines.append("_No research plans logged (pipeline may be using legacy path)._")
    lines.append("")

    # Per-query detail (top 20)
    per_query = [e for e in events if e["event"] == "research.query_fired"]
    if per_query:
        lines.append("### Per-query firing detail")
        lines.append("")
        lines.append("| Agent | Query | Duration | Tool calls | Findings | Citations |")
        lines.append("|---|---|---|---|---|---|")
        for q in per_query[:20]:
            qtext = str(q.get("query", ""))[:60].replace("|", "\\|")
            lines.append(
                f"| {q.get('agent','?')} | {qtext} | "
                f"{q.get('duration_ms',0)/1000:.1f}s | "
                f"{q.get('tool_call_count','?')} | "
                f"{q.get('finding_count','?')} | "
                f"{q.get('citation_count','?')} |"
            )
        if len(per_query) > 20:
            lines.append(f"_(+{len(per_query) - 20} more per-query rows)_")
        lines.append("")

    # Citation freshness roll-up
    citations = [e for e in events if e["event"] == "research.citations"]
    if citations:
        lines.append("## Citation freshness")
        lines.append("")
        lines.append("| Agent | Citations | Fresh (<=1y) | Recent (1-2y) | Older (>2y) | Unknown |")
        lines.append("|---|---|---|---|---|---|")
        totals = {"fresh": 0, "recent": 0, "older": 0, "unknown": 0, "count": 0}
        for c in citations:
            fresh = c.get("freshness", {}).get("distribution", {})
            lines.append(
                f"| {c['agent']} | {c.get('citation_count', 0)} | "
                f"{fresh.get('fresh', 0)} | {fresh.get('recent', 0)} | "
                f"{fresh.get('older', 0)} | {fresh.get('unknown', 0)} |"
            )
            for k in ("fresh", "recent", "older", "unknown"):
                totals[k] += fresh.get(k, 0)
            totals["count"] += c.get("citation_count", 0)
        lines.append(
            f"| **Total** | **{totals['count']}** | **{totals['fresh']}** | "
            f"**{totals['recent']}** | **{totals['older']}** | **{totals['unknown']}** |"
        )
        staleness_warnings = [
            e for e in events if e["event"] == "research.staleness_warning"
        ]
        if staleness_warnings:
            lines.append("")
            lines.append(
                f"⚠️  Staleness warnings: {len(staleness_warnings)} "
                f"(agents where older citations outnumber fresh ones)"
            )
        lines.append("")

    # Hallucination signals
    lines.append("## Grounding signals (lower is better)")
    lines.append("")
    halluc = [e for e in events if e["event"] == "research.quality"]
    if halluc:
        total_warnings = sum(1 for e in halluc if e.get("data_quality_warning_present"))
        total_no_sources = sum(int(e.get("claims_without_sources", 0)) for e in halluc)
        lines.append(f"- Agents with data_quality_warning: **{total_warnings}/{len(halluc)}**")
        lines.append(f"- Claims without a source URL (across agents): **{total_no_sources}**")
        low_confs = sum(
            int(e.get("confidence_distribution", {}).get("low", 0)) for e in halluc
        )
        lines.append(f"- Dimension blocks at confidence=low: **{low_confs}**")
    else:
        lines.append("_No research.quality events._")
    lines.append("")

    # Sources (all)
    lines.append("## Sources cited")
    lines.append("")
    all_urls: list[tuple[str, str]] = []
    for c in citations:
        for u in c.get("urls", []) or []:
            all_urls.append((c["agent"], u))
    if all_urls:
        for agent, url in all_urls[:60]:
            lines.append(f"- `{agent}` · {url}")
        if len(all_urls) > 60:
            lines.append(f"- _(+{len(all_urls)-60} more — see events.jsonl)_")
    else:
        lines.append("_No citations captured._")
    lines.append("")

    # Chart sanitizer fixes
    sanitizer_events = [e for e in events if e["event"] == "chart.sanitizer_applied"]
    if sanitizer_events:
        lines.append("## Chart sanitizer fixes applied")
        lines.append("")
        for ev in sanitizer_events:
            fixes = ev.get("fixes", []) or []
            lines.append(f"- Total fixes this run: **{ev.get('total_fixes', 0)}**")
            for f in fixes[:10]:
                lines.append(f"  - chart {f.get('chart_index')}: {f.get('fix')}")
        lines.append("")

    # Errors
    errors = [e for e in events if e["event"] == "agent.error"]
    render_errors = [e for e in events if e["event"] == "render.mermaid_error"]
    query_errors = [e for e in events if e["event"] == "research.query_error"]
    if errors or render_errors or query_errors:
        lines.append("## Errors")
        lines.append("")
        for e in errors:
            lines.append(
                f"- `{e['agent']}` · {e.get('error_type', '?')} "
                f"(status={e.get('status_code')}): {str(e.get('message', ''))[:200]}"
            )
        for e in query_errors:
            lines.append(
                f"- query failed · `{e.get('agent','?')}` · "
                f"\"{str(e.get('query',''))[:80]}\" · "
                f"{e.get('error_type','?')}: {str(e.get('message',''))[:200]}"
            )
        for e in render_errors:
            lines.append(
                f"- mermaid chart {e.get('chart_index', '?')}: {str(e.get('error', ''))[:200]}"
            )
        lines.append("")

    lines.append("---")
    lines.append("_Generated by app.observability.summary._")
    return "\n".join(lines)


def _group_llm_by_agent(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Aggregate llm.response token counts by agent, folding sub-agent suffixes.

    Research engine emits agent names like `market_sizing::query` and
    `market_sizing::synthesis`; we roll these up under the parent agent name.
    """
    out: dict[str, dict[str, int]] = {}
    for e in events:
        if e.get("event") != "llm.response":
            continue
        agent = str(e.get("agent", "?"))
        root = agent.split("::", 1)[0]
        bucket = out.setdefault(root, {"in": 0, "out": 0})
        bucket["in"] += int(e.get("input_tokens", 0))
        bucket["out"] += int(e.get("output_tokens", 0))
    return out
