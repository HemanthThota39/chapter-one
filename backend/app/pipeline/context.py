from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ResearchBundle:
    orchestrator: dict[str, Any]
    market: dict[str, Any]
    competitors: dict[str, Any]
    timing: dict[str, Any]
    regulatory: dict[str, Any]

    def as_context_blob(self) -> str:
        """Merged research context block passed to analysis agents."""
        return json.dumps(
            {
                "orchestrator": self.orchestrator,
                "market_research": self.market,
                "competitor_research": self.competitors,
                "timing_research": self.timing,
                "regulatory_research": self.regulatory,
            },
            indent=2,
            default=str,
        )


@dataclass
class AnalysisBundle:
    research: ResearchBundle
    problem_pmf: dict[str, Any]
    business_model: dict[str, Any]
    gtm_team: dict[str, Any]
    risk_moat: dict[str, Any]


@dataclass
class FullBundle:
    analysis: AnalysisBundle
    scoring: dict[str, Any]
