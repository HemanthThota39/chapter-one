from enum import StrEnum


class CvfDimension(StrEnum):
    PROBLEM_SEVERITY = "d1_problem_severity"
    MARKET_SIZE = "d2_market_size"
    SOLUTION_PMF = "d3_solution_pmf"
    BUSINESS_MODEL = "d4_business_model"
    COMPETITIVE_MOAT = "d5_competitive_moat"
    MARKET_TIMING = "d6_market_timing"
    GTM = "d7_gtm"
    TEAM_FIT = "d8_team_fit"
    TRACTION = "d9_traction"
    RISK_PROFILE = "d10_risk_profile"


# Note: The original plan listed weights that summed to 110% (a bug). We fixed
# this by reducing Problem Severity and Market Size from 15% to 10% each so
# weights sum to exactly 100%. All other weights preserved from the plan.
DIMENSION_WEIGHTS: dict[CvfDimension, float] = {
    CvfDimension.PROBLEM_SEVERITY: 0.10,
    CvfDimension.MARKET_SIZE: 0.10,
    CvfDimension.SOLUTION_PMF: 0.10,
    CvfDimension.BUSINESS_MODEL: 0.10,
    CvfDimension.COMPETITIVE_MOAT: 0.12,
    CvfDimension.MARKET_TIMING: 0.10,
    CvfDimension.GTM: 0.10,
    CvfDimension.TEAM_FIT: 0.08,
    CvfDimension.TRACTION: 0.10,
    CvfDimension.RISK_PROFILE: 0.10,
}

DIMENSION_LABELS: dict[CvfDimension, str] = {
    CvfDimension.PROBLEM_SEVERITY: "Problem severity",
    CvfDimension.MARKET_SIZE: "Market size",
    CvfDimension.SOLUTION_PMF: "Solution + PMF",
    CvfDimension.BUSINESS_MODEL: "Business model",
    CvfDimension.COMPETITIVE_MOAT: "Competitive moat",
    CvfDimension.MARKET_TIMING: "Market timing",
    CvfDimension.GTM: "Go-to-market",
    CvfDimension.TEAM_FIT: "Team fit",
    CvfDimension.TRACTION: "Traction",
    CvfDimension.RISK_PROFILE: "Risk profile",
}


def verdict_from_score(score_100: int) -> str:
    if score_100 >= 75:
        return "STRONG INVEST"
    if score_100 >= 60:
        return "CONDITIONAL"
    if score_100 >= 45:
        return "WATCH"
    if score_100 >= 30:
        return "PASS"
    return "HARD PASS"
