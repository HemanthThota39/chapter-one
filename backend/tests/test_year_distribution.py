from app.observability.extractors import year_distribution


def test_urls_with_years_in_path():
    urls = [
        "https://example.com/2026/article",
        "https://example.com/2025/article",
        "https://example.com/2020/old",
        "https://example.com/no-year",
    ]
    dist = year_distribution(urls)
    assert dist["distribution"]["fresh"] >= 1
    assert dist["distribution"]["older"] >= 1
    assert dist["distribution"]["unknown"] >= 1
    assert dist["sample_size"] == 3


def test_findings_with_explicit_date():
    findings = [
        {"fact": "x", "source_url": "https://a.com", "date": "2026-01-15"},
        {"fact": "y", "source_url": "https://b.com", "date": "2024"},
        {"fact": "z", "source_url": "https://c.com", "date": ""},
    ]
    dist = year_distribution(findings)
    assert dist["sample_size"] == 2
    assert dist["max_year"] == 2026
    assert dist["min_year"] == 2024


def test_empty_input():
    dist = year_distribution([])
    assert dist["sample_size"] == 0
    assert dist["avg_year"] is None
    assert all(v == 0 for v in dist["distribution"].values())
