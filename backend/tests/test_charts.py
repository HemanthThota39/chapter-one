"""Smoke tests for server-side chart generators."""

from app.core.charts import (
    _format_usd,
    _score_color,
    render_competitive_landscape,
    render_cvf_dashboard,
    render_market_opportunity,
    render_revenue_trajectory,
    render_risk_matrix,
    substitute_charts,
)


SAMPLE_DATA = {
    "scoring": {
        "scorecard": {
            "d1_problem_severity": {"score": 7, "weight": 0.10, "weighted": 0.70},
            "d2_market_size": {"score": 8, "weight": 0.10, "weighted": 0.80},
            "d3_solution_pmf": {"score": 6, "weight": 0.10, "weighted": 0.60},
            "d4_business_model": {"score": 5, "weight": 0.10, "weighted": 0.50},
            "d5_competitive_moat": {"score": 4, "weight": 0.12, "weighted": 0.48},
            "d6_market_timing": {"score": 9, "weight": 0.10, "weighted": 0.90},
            "d7_gtm": {"score": 6, "weight": 0.10, "weighted": 0.60},
            "d8_team_fit": {"score": 7, "weight": 0.08, "weighted": 0.56},
            "d9_traction": {"score": 5, "weight": 0.10, "weighted": 0.50},
            "d10_risk_profile": {"score": 6, "weight": 0.10, "weighted": 0.60},
        },
        "overall_score_100": 63,
        "verdict": "CONDITIONAL",
    },
    "market": {
        "tam": {"value_usd": 11.02, "unit": "billion"},
        "sam": {"value_usd": 3.3, "unit": "billion"},
        "som_y3": {"value_usd": 99, "unit": "million"},
    },
    "competitors": {
        "direct_competitors": [
            {"name": "Otter.ai", "funding_stage": "series-b", "threat_level": "critical"},
            {"name": "Fireflies.ai", "funding_stage": "series-a", "threat_level": "critical"},
            {"name": "Fathom", "funding_stage": "seed", "threat_level": "high"},
        ],
    },
    "orchestrator": {"idea_title": "Test Startup"},
    "risk_moat": {
        "dimension_10_risk_profile": {
            "risks": [
                {"risk_type": "technical", "description": "Model drift", "probability": "medium", "impact": "high"},
                {"risk_type": "competitive", "description": "Incumbent response", "probability": "high", "impact": "critical"},
                {"risk_type": "market", "description": "Adoption lag", "probability": "low", "impact": "medium"},
            ]
        }
    },
}


def test_cvf_dashboard_renders_svg():
    svg = render_cvf_dashboard(SAMPLE_DATA)
    assert svg is not None
    assert svg.startswith("<svg")
    assert "CVF dimension scores" in svg
    # Verdict callout
    assert "63/100" in svg and "CONDITIONAL" in svg


def test_market_opportunity_renders_svg():
    svg = render_market_opportunity(SAMPLE_DATA)
    assert svg is not None
    assert svg.startswith("<svg")
    # Labels should be present
    assert "TAM" in svg
    assert "SAM" in svg


def test_competitive_landscape_places_our_startup():
    svg = render_competitive_landscape(SAMPLE_DATA)
    assert svg is not None
    assert "Otter.ai" in svg
    assert "Test Startup" in svg


def test_risk_matrix_renders():
    svg = render_risk_matrix(SAMPLE_DATA)
    assert svg is not None
    assert "Risk matrix" in svg


def test_revenue_trajectory_renders_from_som():
    svg = render_revenue_trajectory(SAMPLE_DATA)
    assert svg is not None
    assert "Year 3" in svg


def test_substitute_replaces_placeholders():
    md = """# Report
## Section
<!-- CHART:cvf_dashboard -->
some text
<!-- CHART:market_opportunity -->
more text"""
    out, rendered = substitute_charts(md, SAMPLE_DATA)
    assert "<!-- CHART:cvf_dashboard -->" not in out
    assert "<!-- CHART:market_opportunity -->" not in out
    assert rendered == ["cvf_dashboard", "market_opportunity"]
    assert out.count("<svg") == 2


def test_substitute_with_missing_data_skips_gracefully():
    md = '<!-- CHART:market_opportunity -->'
    out, rendered = substitute_charts(md, {})
    assert "chart `market_opportunity` skipped" in out
    assert rendered == []


def test_substitute_unknown_chart_is_skipped():
    md = '<!-- CHART:nonexistent -->'
    out, _ = substitute_charts(md, SAMPLE_DATA)
    assert "chart `nonexistent` skipped" in out


def test_score_color_thresholds():
    assert _score_color(9) == _score_color(7)  # both HIGH
    assert _score_color(5) == _score_color(6)  # both MID
    assert _score_color(1) == _score_color(4)  # both LOW
    assert _score_color(7) != _score_color(5)  # cross threshold


def test_format_usd_units():
    assert _format_usd(1500) == "$1.50B"
    assert _format_usd(250) == "$250.0M"
    assert _format_usd(0.5) == "$500K"
    assert _format_usd(0) == "—"
