import json
from pathlib import Path

from app.observability.metrics import (
    aggregate_across_analyses,
    per_analysis_stats,
    read_events,
)


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def test_per_analysis_stats_basic(tmp_path: Path):
    path = tmp_path / "abc" / "events.jsonl"
    _write_events(
        path,
        [
            {"event": "pipeline.start", "idea_chars": 120},
            {"event": "agent.start", "agent": "orchestrator"},
            {"event": "llm.response", "agent": "orchestrator", "input_tokens": 100, "output_tokens": 50},
            {"event": "agent.complete", "agent": "orchestrator", "duration_ms": 1200},
            {"event": "agent.start", "agent": "market_sizing"},
            {"event": "llm.response", "agent": "market_sizing", "input_tokens": 300, "output_tokens": 120},
            {"event": "research.tool_calls", "agent": "market_sizing", "tool_call_count": 3},
            {
                "event": "research.citations",
                "agent": "market_sizing",
                "urls": ["https://a.com", "https://b.com"],
                "citation_count": 2,
                "unique_domains": 2,
            },
            {"event": "research.quality", "agent": "market_sizing",
             "data_quality_warning_present": True, "claims_without_sources": 1,
             "confidence_distribution": {"high": 0, "medium": 1, "low": 0}},
            {"event": "agent.complete", "agent": "market_sizing", "duration_ms": 8400},
            {"event": "agent.error", "agent": "competitive_intel", "error_type": "BadRequestError"},
            {"event": "pipeline.complete", "duration_ms": 12000, "overall_score_100": 52, "verdict": "WATCH"},
        ],
    )
    events = read_events(path)
    stats = per_analysis_stats(events)

    assert stats["agents_completed"] == 2
    assert stats["agents_errored"] == ["competitive_intel"]
    assert stats["total_tokens_in"] == 400
    assert stats["total_tokens_out"] == 170
    assert stats["total_urls_cited"] == 2
    assert stats["total_web_searches"] == 3
    assert stats["hallucination"]["data_quality_warnings"] == 1
    assert stats["pipeline"]["verdict"] == "WATCH"


def test_aggregate_across_empty_dir(tmp_path: Path):
    agg = aggregate_across_analyses(tmp_path)
    assert agg == {"count": 0}


def test_aggregate_computes_latency_per_agent(tmp_path: Path):
    for aid, dur in [("a1", 1000), ("a2", 2000), ("a3", 3000)]:
        _write_events(
            tmp_path / aid / "events.jsonl",
            [
                {"event": "agent.complete", "agent": "market_sizing", "duration_ms": dur},
            ],
        )
    agg = aggregate_across_analyses(tmp_path)
    assert agg["count"] == 3
    ms = agg["latency_by_agent"]["market_sizing"]
    assert ms["p50_ms"] == 2000
    assert ms["max_ms"] == 3000
    assert ms["n"] == 3
