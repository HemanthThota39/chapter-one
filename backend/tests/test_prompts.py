from app.prompts.library import (
    PROMPT_0_SYSTEM,
    PROMPT_1_ORCHESTRATOR,
    PROMPT_2_MARKET_SIZING,
    PROMPT_3_COMPETITIVE,
    PROMPT_4_NEWS_TRENDS,
    PROMPT_5_REGULATORY,
    PROMPT_6_PROBLEM_PMF,
    PROMPT_7_BUSINESS_MODEL,
    PROMPT_8_GTM_TEAM,
    PROMPT_9_RISK_MOAT,
    PROMPT_10_SCORING,
    PROMPT_11_REPORT,
)


def test_system_prompt_has_grounding_requirement():
    assert "Operating principles" in PROMPT_0_SYSTEM
    assert "web search" in PROMPT_0_SYSTEM.lower()
    assert "Scoring rubric" in PROMPT_0_SYSTEM


def test_orchestrator_formats():
    rendered = PROMPT_1_ORCHESTRATOR.format(user_idea="a test idea")
    assert "a test idea" in rendered
    assert "search_queries" in rendered


def test_market_sizing_formats():
    # Synthesis prompt — queries are driven by the research engine, not embedded here
    rendered = PROMPT_2_MARKET_SIZING.format(
        idea_title="X", one_liner="Y", industry="Z", sub_sector="S",
        target_customer="T", geography_focus="G",
    )
    assert "synthesis agent" in rendered.lower()
    assert "X" in rendered
    assert "Z" in rendered


def test_report_template_has_all_charts():
    rendered = PROMPT_11_REPORT.format(
        orchestrator_output="{}",
        market_research_output="{}",
        competitor_research_output="{}",
        timing_research_output="{}",
        regulatory_research_output="{}",
        problem_pmf_output="{}",
        business_model_output="{}",
        gtm_team_output="{}",
        risk_moat_output="{}",
        scoring_output="{}",
    )
    # All 5 chart placeholders present (now rendered server-side from structured data)
    assert "<!-- CHART:cvf_dashboard -->" in rendered
    assert "<!-- CHART:market_opportunity -->" in rendered
    assert "<!-- CHART:competitive_landscape -->" in rendered
    assert "<!-- CHART:risk_matrix -->" in rendered
    assert "<!-- CHART:revenue_trajectory -->" in rendered


def test_all_prompts_importable():
    for p in [
        PROMPT_3_COMPETITIVE, PROMPT_4_NEWS_TRENDS, PROMPT_5_REGULATORY,
        PROMPT_6_PROBLEM_PMF, PROMPT_7_BUSINESS_MODEL, PROMPT_8_GTM_TEAM,
        PROMPT_9_RISK_MOAT, PROMPT_10_SCORING,
    ]:
        assert isinstance(p, str) and len(p) > 100
