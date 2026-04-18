"""Research engine tests — cover QueryResult surface + _loads_lenient fallback."""

from app.pipeline.research_engine import (
    QueryResult,
    _loads_lenient,
)


def test_queryresult_citation_count():
    r = QueryResult(query="x", agent="a", urls=["https://a.com", "https://b.com"])
    assert r.citation_count == 2


def test_queryresult_summarise_caps_findings():
    findings = [{"fact": f"f{i}", "source_url": f"https://x/{i}"} for i in range(50)]
    r = QueryResult(query="x", agent="a", findings=findings, urls=["https://x/0"])
    summary = r.summarise_for_synthesis()
    assert len(summary["findings"]) == 30
    assert summary["citations"] == ["https://x/0"]


def test_loads_lenient_strips_code_fence():
    text = "```json\n{\"a\": 1}\n```"
    assert _loads_lenient(text) == {"a": 1}


def test_loads_lenient_extracts_json_from_preamble():
    text = "Sure, here is the JSON:\n{\"a\": 1, \"b\": 2}\nThat's it."
    assert _loads_lenient(text) == {"a": 1, "b": 2}


def test_loads_lenient_returns_parse_error_on_garbage():
    text = "totally not json at all"
    result = _loads_lenient(text)
    assert result.get("parse_error") is True
    assert "raw" in result
