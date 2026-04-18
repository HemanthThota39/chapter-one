from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class TargetCustomer(BaseModel):
    primary: str
    secondary: str = ""


class SearchQueries(BaseModel):
    market_sizing: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    news_trends: list[str] = Field(default_factory=list)
    regulations: list[str] = Field(default_factory=list)


class OrchestratorOutput(BaseModel):
    idea_title: str
    one_liner: str
    problem_statement: str
    proposed_solution: str
    industry: str
    sub_sector: str
    target_customer: TargetCustomer
    geography_focus: str
    business_model_type: str
    revenue_model: str
    technology_category: str
    stage_assumption: str = "pre-idea"
    search_queries: SearchQueries
    ambiguities: list[str] = Field(default_factory=list)


class SourcedFigure(BaseModel):
    value_usd: float
    unit: Literal["billion", "million"] = "billion"
    source: str = ""
    source_url: str = ""
    year: int | None = None
    confidence: Confidence = "low"
    notes: str = ""


class MarketSizingOutput(BaseModel):
    tam: SourcedFigure
    sam: dict[str, Any]
    som_y3: dict[str, Any]
    market_cagr: dict[str, Any]
    market_maturity: str = "emerging"
    secondary_sources: list[dict[str, Any]] = Field(default_factory=list)
    data_quality_warning: str = ""


class CompetitorEntry(BaseModel):
    name: str
    url: str = ""
    founded: int | None = None
    funding_total_usd: str = "Unknown"
    funding_stage: str = "unknown"
    last_funding_date: str = "Unknown"
    key_differentiator: str = ""
    estimated_customers: str = "Unknown"
    threat_level: Literal["low", "medium", "high", "critical"] = "medium"
    source_url: str = ""


class IndirectCompetitor(BaseModel):
    name: str
    url: str = ""
    overlap: str = ""
    threat_level: Literal["low", "medium", "high"] = "low"


class PortersAnalysis(BaseModel):
    new_entrant_threat: Literal["low", "medium", "high"] = "medium"
    new_entrant_reasoning: str = ""
    customer_switching_cost: Literal["low", "medium", "high"] = "medium"
    switching_reasoning: str = ""
    substitute_threat: Literal["low", "medium", "high"] = "medium"
    substitute_reasoning: str = ""
    overall_competitive_intensity: Literal["fragmented", "competitive", "consolidated"] = (
        "competitive"
    )


class CompetitiveIntelOutput(BaseModel):
    direct_competitors: list[CompetitorEntry] = Field(default_factory=list)
    indirect_competitors: list[IndirectCompetitor] = Field(default_factory=list)
    market_leaders: list[str] = Field(default_factory=list)
    porters_analysis: PortersAnalysis
    white_space: str = ""
    data_quality_warning: str = ""


class TimingSignal(BaseModel):
    signal_type: str
    description: str
    date: str = ""
    source: str = ""
    source_url: str = ""
    relevance: Literal["direct", "indirect"] = "direct"
    strength: Literal["weak", "moderate", "strong"] = "moderate"


class FundingRound(BaseModel):
    company: str
    amount: str = ""
    date: str = ""
    investor: str = ""
    source_url: str = ""


class NewsTrendsOutput(BaseModel):
    why_now_signals: list[TimingSignal] = Field(default_factory=list)
    recent_funding_in_space: list[FundingRound] = Field(default_factory=list)
    technology_tailwinds: str = ""
    headwinds: str = ""
    wave_timing: Literal["too_early", "early", "on_time", "late", "too_late"] = "on_time"
    wave_timing_reasoning: str = ""
    overall_timing_score: int = 5
    data_quality_warning: str = ""


class RegulatoryFramework(BaseModel):
    name: str
    jurisdiction: str
    applicability: Literal["direct", "indirect", "potential"] = "direct"
    compliance_cost: Literal["low", "medium", "high", "unknown"] = "unknown"
    description: str = ""
    source_url: str = ""


class LicensingRequirement(BaseModel):
    type: str
    jurisdiction: str = ""
    difficulty: Literal["easy", "moderate", "hard", "prohibitive"] = "moderate"
    estimated_timeline_months: int = 0
    source_url: str = ""


class RegulatoryOutput(BaseModel):
    regulatory_frameworks: list[RegulatoryFramework] = Field(default_factory=list)
    licensing_requirements: list[LicensingRequirement] = Field(default_factory=list)
    regulatory_risk_score: int = 5
    regulatory_moat_potential: bool = False
    regulatory_moat_reasoning: str = ""
    key_risks: list[str] = Field(default_factory=list)
    data_quality_warning: str = ""


class DimensionAnalysis(BaseModel):
    score: int
    score_justification: str = ""
    confidence: Confidence = "medium"
    red_flags: list[str] = Field(default_factory=list)
    # free-form fields vary by dimension — kept open
    extra: dict[str, Any] = Field(default_factory=dict)


class ProblemPmfOutput(BaseModel):
    dimension_1_problem_severity: dict[str, Any]
    dimension_3_solution_pmf: dict[str, Any]


class BusinessModelOutput(BaseModel):
    dimension_2_market_size: dict[str, Any]
    dimension_4_business_model: dict[str, Any]
    dimension_6_market_timing: dict[str, Any]


class GtmTeamOutput(BaseModel):
    dimension_7_gtm: dict[str, Any]
    dimension_8_team_fit: dict[str, Any]


class RiskMoatOutput(BaseModel):
    dimension_5_competitive_moat: dict[str, Any]
    dimension_9_traction: dict[str, Any]
    dimension_10_risk_profile: dict[str, Any]


class ScorecardEntry(BaseModel):
    score: int
    weight: float
    weighted: float


class ScoringOutput(BaseModel):
    scorecard: dict[str, ScorecardEntry]
    overall_score_10: float
    overall_score_100: int
    verdict: str
    verdict_reasoning: str = ""
    top_3_strengths: list[str] = Field(default_factory=list)
    top_3_weaknesses: list[str] = Field(default_factory=list)
    critical_conditions: list[str] = Field(default_factory=list)
    next_experiment: str = ""


class AnalysisRequest(BaseModel):
    idea: str = Field(..., min_length=20, max_length=4000)


class AnalysisStartResponse(BaseModel):
    analysis_id: str
    status: Literal["queued", "running"] = "queued"


class ProgressEvent(BaseModel):
    stage: str
    percent: int
    message: str = ""
