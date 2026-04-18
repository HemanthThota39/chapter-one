from app.observability.extractors import (
    extract_usage,
    hallucination_signals,
    scan_parsed_for_urls,
)


class _Obj:
    """Shim for tests that mimics SDK attribute-access."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_extract_usage_chat_completions_shape():
    resp = _Obj(usage=_Obj(prompt_tokens=42, completion_tokens=17))
    assert extract_usage(resp) == {"input_tokens": 42, "output_tokens": 17}


def test_extract_usage_responses_api_shape():
    resp = _Obj(usage=_Obj(input_tokens=100, output_tokens=200))
    assert extract_usage(resp) == {"input_tokens": 100, "output_tokens": 200}


def test_extract_usage_missing():
    assert extract_usage(_Obj()) == {"input_tokens": 0, "output_tokens": 0}


def test_scan_parsed_for_urls_finds_all_url_keys():
    parsed = {
        "tam": {"source_url": "https://statista.com/x"},
        "competitors": [
            {"source_url": "https://crunchbase.com/y"},
            {"url": "https://ignored.com"},  # key doesn't end in _url, ignored
        ],
    }
    urls = scan_parsed_for_urls(parsed)
    assert "https://statista.com/x" in urls
    assert "https://crunchbase.com/y" in urls
    assert "https://ignored.com" not in urls


def test_hallucination_signals_flags_missing_sources():
    parsed = {
        "direct_competitors": [
            {"name": "Acme", "funding_stage": "seed", "source_url": "https://a.com"},
            {"name": "Fake", "funding_stage": "series-a"},  # no source
        ],
        "tam": {"value_usd": 50, "source_url": "https://s.com"},
        "data_quality_warning": "Some gaps",
        "dim": {"confidence": "low"},
    }
    signals = hallucination_signals(parsed)
    assert signals["data_quality_warning_present"] is True
    assert signals["claims_without_sources"] >= 1
    assert signals["confidence_distribution"]["low"] == 1


def test_hallucination_signals_clean_payload():
    parsed = {"dim": {"confidence": "high", "score": 8}}
    signals = hallucination_signals(parsed)
    assert signals["data_quality_warning_present"] is False
    assert signals["confidence_distribution"]["high"] == 1
