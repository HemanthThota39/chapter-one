import json
from pathlib import Path

from app.observability.summary import build_summary


def test_build_summary_renders_all_sections(tmp_path: Path):
    d = tmp_path / "xyz"
    d.mkdir()
    (d / "events.jsonl").write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                {"event": "pipeline.start", "ts": 1713400000, "idea_chars": 120},
                {"event": "agent.start", "agent": "market_sizing"},
                {
                    "event": "llm.response",
                    "agent": "market_sizing",
                    "input_tokens": 400,
                    "output_tokens": 180,
                },
                {
                    "event": "research.tool_calls",
                    "agent": "market_sizing",
                    "tool_call_count": 4,
                },
                {
                    "event": "research.citations",
                    "agent": "market_sizing",
                    "urls": ["https://statista.com/x", "https://gartner.com/y"],
                    "citation_count": 2,
                    "unique_domains": 2,
                },
                {
                    "event": "research.quality",
                    "agent": "market_sizing",
                    "data_quality_warning_present": False,
                    "claims_without_sources": 0,
                    "confidence_distribution": {"high": 1, "medium": 0, "low": 0},
                },
                {
                    "event": "agent.complete",
                    "agent": "market_sizing",
                    "duration_ms": 7500,
                },
                {
                    "event": "pipeline.complete",
                    "duration_ms": 42000,
                    "overall_score_100": 68,
                    "verdict": "CONDITIONAL",
                },
            ]
        )
    )
    md = build_summary(d)
    assert "Analysis xyz" in md
    assert "CONDITIONAL" in md
    assert "market_sizing" in md
    assert "https://statista.com/x" in md
    assert "Grounding signals" in md


def test_build_summary_empty_dir_is_safe(tmp_path: Path):
    md = build_summary(tmp_path / "nothing")
    assert "No events logged" in md
