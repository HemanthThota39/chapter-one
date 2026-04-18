from app.models.schemas import (
    AnalysisRequest,
    OrchestratorOutput,
    SearchQueries,
    TargetCustomer,
)


def test_analysis_request_length_validation():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalysisRequest(idea="too short")

    AnalysisRequest(idea="this is a long enough idea for the validator to accept it now")


def test_orchestrator_output_roundtrip():
    payload = {
        "idea_title": "CA Copilot",
        "one_liner": "AI for CA firms",
        "problem_statement": "GST filing is painful",
        "proposed_solution": "AI copilot",
        "industry": "FinTech",
        "sub_sector": "SMB compliance",
        "target_customer": {"primary": "CA firms", "secondary": "SMBs"},
        "geography_focus": "India",
        "business_model_type": "SaaS",
        "revenue_model": "subscription",
        "technology_category": "AI/ML",
        "stage_assumption": "pre-idea",
        "search_queries": {
            "market_sizing": ["q1"],
            "competitors": ["q2"],
            "news_trends": ["q3"],
            "regulations": ["q4"],
        },
        "ambiguities": [],
    }
    parsed = OrchestratorOutput.model_validate(payload)
    assert parsed.idea_title == "CA Copilot"
    assert parsed.target_customer.primary == "CA firms"
    assert parsed.search_queries.market_sizing == ["q1"]


def test_target_customer_defaults():
    tc = TargetCustomer(primary="freelancers")
    assert tc.secondary == ""


def test_search_queries_defaults():
    q = SearchQueries()
    assert q.market_sizing == []
    assert q.regulations == []
