"""Deterministic server-side chart generation.

Replaces LLM-generated Mermaid blocks. The report compiler emits
placeholder markers (e.g. `<!-- CHART:cvf_dashboard -->`) and this module
substitutes them with inline SVG generated from the structured pipeline data.

Guarantees:
- Zero dependency on the LLM producing valid chart syntax
- Charts always render (SVG is universal)
- `.md` file stays self-contained and downloadable
"""

from __future__ import annotations

import io
import logging
import re
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

matplotlib.use("Agg")  # headless

log = logging.getLogger(__name__)

# Placeholder format: <!-- CHART:name -->
CHART_PLACEHOLDER_RE = re.compile(r"<!--\s*CHART:([a-z_]+)\s*-->", re.IGNORECASE)

# Palette — subtle, print-friendly, colour-blind safe
COLOR_HIGH = "#16a34a"   # green-600
COLOR_MID = "#ca8a04"    # yellow-700
COLOR_LOW = "#dc2626"    # red-600
COLOR_ACCENT = "#2563eb" # blue-600
COLOR_MUTED = "#6b7280"  # grey-500
COLOR_GRID = "#e5e7eb"   # grey-200


DIMENSION_LABELS_ORDERED = [
    ("d1_problem_severity", "Problem severity"),
    ("d2_market_size", "Market size"),
    ("d3_solution_pmf", "Solution + PMF"),
    ("d4_business_model", "Business model"),
    ("d5_competitive_moat", "Competitive moat"),
    ("d6_market_timing", "Market timing"),
    ("d7_gtm", "Go-to-market"),
    ("d8_team_fit", "Team fit"),
    ("d9_traction", "Traction"),
    ("d10_risk_profile", "Risk profile"),
]


def substitute_charts(markdown: str, data: dict[str, Any]) -> tuple[str, list[str]]:
    """Replace every <!-- CHART:name --> placeholder with an inline SVG block.

    Returns (new_markdown, list_of_chart_names_rendered).
    """
    rendered: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        try:
            svg = _render_chart(name, data)
            if svg is None:
                return f"\n*_(chart `{name}` skipped — insufficient data)_*\n"
            rendered.append(name)
            # Wrap the raw SVG in a div so react-markdown + rehype-raw render it cleanly.
            return (
                f"\n<div class=\"chart-block\" data-chart=\"{name}\">\n"
                f"{svg}\n"
                f"</div>\n"
            )
        except Exception as e:  # noqa: BLE001
            log.exception("Chart '%s' failed to render", name)
            return f"\n*_(chart `{name}` failed: {type(e).__name__})_*\n"

    new_md = CHART_PLACEHOLDER_RE.sub(_replace, markdown)
    return new_md, rendered


def _render_chart(name: str, data: dict[str, Any]) -> str | None:
    """Dispatch to the chart builder."""
    renderers = {
        "cvf_dashboard": render_cvf_dashboard,
        "market_opportunity": render_market_opportunity,
        "competitive_landscape": render_competitive_landscape,
        "risk_matrix": render_risk_matrix,
        "revenue_trajectory": render_revenue_trajectory,
    }
    fn = renderers.get(name)
    if fn is None:
        return None
    return fn(data)


# ---------------------------------------------------------------------------
# 1. CVF Score Dashboard — horizontal bar
# ---------------------------------------------------------------------------

def render_cvf_dashboard(data: dict[str, Any]) -> str | None:
    scoring = data.get("scoring") or {}
    scorecard = scoring.get("scorecard") or {}
    if not scorecard:
        return None

    scores: list[tuple[str, int]] = []
    for key, label in DIMENSION_LABELS_ORDERED:
        entry = scorecard.get(key) or {}
        score = int(entry.get("score") or 0)
        scores.append((label, score))

    labels = [s[0] for s in scores][::-1]  # reverse so top-importance is at top
    values = [s[1] for s in scores][::-1]
    colors = [_score_color(v) for v in values]

    fig, ax = plt.subplots(figsize=(8.2, 4.4), dpi=110)
    y_pos = range(len(labels))
    bars = ax.barh(y_pos, values, color=colors, height=0.6, edgecolor="none")

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, 10)
    ax.set_xticks([0, 2, 4, 6, 8, 10])
    ax.set_xlabel("Score (out of 10)", fontsize=9)
    ax.set_title("CVF dimension scores", fontsize=11, fontweight="bold", pad=10)

    # Value labels at bar ends
    for bar, value in zip(bars, values):
        ax.text(
            value + 0.15, bar.get_y() + bar.get_height() / 2,
            f"{value}", va="center", fontsize=9, color="#111",
        )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_GRID)
    ax.spines["bottom"].set_color(COLOR_GRID)
    ax.tick_params(colors=COLOR_MUTED)
    ax.xaxis.grid(True, linestyle="--", alpha=0.4, color=COLOR_GRID)
    ax.set_axisbelow(True)

    # Add overall score annotation
    overall = scoring.get("overall_score_100") or 0
    verdict = scoring.get("verdict") or ""
    if overall:
        ax.text(
            0.99, 0.98,
            f"Overall: {overall}/100\n{verdict}",
            transform=ax.transAxes,
            ha="right", va="top",
            fontsize=10, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f3f4f6", edgecolor="#d1d5db"),
        )

    return _fig_to_svg(fig)


# ---------------------------------------------------------------------------
# 2. Market Opportunity — TAM / SAM / SOM bar
# ---------------------------------------------------------------------------

def render_market_opportunity(data: dict[str, Any]) -> str | None:
    market = data.get("market") or {}
    if not market:
        return None

    tam = _extract_amount_usd(market.get("tam"))
    sam = _extract_amount_usd(market.get("sam"))
    som = _extract_amount_usd(market.get("som_y3"))

    if not any([tam, sam, som]):
        return None

    labels = ["TAM", "SAM", "SOM (Y3)"]
    values = [tam or 0, sam or 0, som or 0]
    colors = [COLOR_ACCENT, "#60a5fa", "#93c5fd"]

    fig, ax = plt.subplots(figsize=(6.5, 4.0), dpi=110)
    bars = ax.bar(labels, values, color=colors, width=0.55, edgecolor="none")
    ax.set_ylabel("USD (millions)", fontsize=9)
    ax.set_title("Market opportunity", fontsize=11, fontweight="bold", pad=10)

    max_val = max(values) if max(values) > 0 else 1
    ax.set_ylim(0, max_val * 1.2)

    # Value labels above bars with human-readable units
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_val * 0.02,
            _format_usd(value),
            ha="center", fontsize=9, color="#111",
        )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_GRID)
    ax.spines["bottom"].set_color(COLOR_GRID)
    ax.tick_params(colors=COLOR_MUTED)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4, color=COLOR_GRID)
    ax.set_axisbelow(True)

    return _fig_to_svg(fig)


# ---------------------------------------------------------------------------
# 3. Competitive Landscape — scatter quadrant
# ---------------------------------------------------------------------------

_STAGE_TO_PRESENCE = {
    "public": 0.95,
    "series-c": 0.85,
    "series-b": 0.72,
    "series-a": 0.55,
    "seed": 0.32,
    "pre-seed": 0.18,
    "bootstrapped": 0.25,
    "unknown": 0.22,
}


def render_competitive_landscape(data: dict[str, Any]) -> str | None:
    competitors = data.get("competitors") or {}
    direct = competitors.get("direct_competitors") or []
    orchestrator = data.get("orchestrator") or {}
    idea_title = orchestrator.get("idea_title", "Our startup")
    if not direct:
        return None

    # Heuristic positioning — market_presence from funding_stage, differentiation from threat_level
    points: list[tuple[float, float, str]] = []
    for c in direct[:8]:  # cap for readability
        stage = str(c.get("funding_stage", "unknown")).lower()
        presence = _STAGE_TO_PRESENCE.get(stage, 0.3)
        # Differentiation: higher threat → crowding our space → lower differentiation in quadrant
        threat = str(c.get("threat_level", "medium")).lower()
        diff = {"critical": 0.30, "high": 0.45, "medium": 0.60, "low": 0.75}.get(threat, 0.5)
        name = str(c.get("name", ""))[:28] or "?"
        points.append((presence, diff, name))

    fig, ax = plt.subplots(figsize=(7.5, 5.6), dpi=110)

    # Quadrant lines
    ax.axvline(0.5, color=COLOR_GRID, linestyle="--", linewidth=1, zorder=1)
    ax.axhline(0.5, color=COLOR_GRID, linestyle="--", linewidth=1, zorder=1)

    # Quadrant labels (subtle, in corners)
    label_kwargs = dict(fontsize=8, color=COLOR_MUTED, alpha=0.7, style="italic")
    ax.text(0.02, 0.97, "Premium niche", ha="left", va="top", transform=ax.transAxes, **label_kwargs)
    ax.text(0.98, 0.97, "Market leader", ha="right", va="top", transform=ax.transAxes, **label_kwargs)
    ax.text(0.02, 0.03, "Commoditised", ha="left", va="bottom", transform=ax.transAxes, **label_kwargs)
    ax.text(0.98, 0.03, "Threat zone", ha="right", va="bottom", transform=ax.transAxes, **label_kwargs)

    # Competitor points
    for x, y, name in points:
        ax.scatter(x, y, s=120, c=COLOR_LOW, alpha=0.7, edgecolor="white", linewidth=1.5, zorder=3)
        ax.annotate(name, (x, y), textcoords="offset points", xytext=(8, 4), fontsize=8)

    # Our startup — distinct colour
    ax.scatter(0.18, 0.78, s=200, c=COLOR_ACCENT, alpha=0.9, edgecolor="white", linewidth=2, zorder=4, marker="*")
    ax.annotate(idea_title[:30], (0.18, 0.78), textcoords="offset points", xytext=(10, 6), fontsize=9, fontweight="bold", color=COLOR_ACCENT)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Market presence  →", fontsize=9)
    ax.set_ylabel("Product differentiation  →", fontsize=9)
    ax.set_title("Competitive positioning (heuristic from funding + threat signals)", fontsize=10, fontweight="bold", pad=10)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(COLOR_GRID)

    return _fig_to_svg(fig)


# ---------------------------------------------------------------------------
# 4. Risk Matrix — probability × impact scatter
# ---------------------------------------------------------------------------

_LEVEL = {"low": 0.2, "medium": 0.55, "high": 0.85, "critical": 0.95}


def render_risk_matrix(data: dict[str, Any]) -> str | None:
    risk_moat = data.get("risk_moat") or {}
    risks = (risk_moat.get("dimension_10_risk_profile") or {}).get("risks") or []
    if not risks:
        return None

    fig, ax = plt.subplots(figsize=(7.5, 5.6), dpi=110)
    ax.axvline(0.5, color=COLOR_GRID, linestyle="--", linewidth=1, zorder=1)
    ax.axhline(0.5, color=COLOR_GRID, linestyle="--", linewidth=1, zorder=1)

    label_kwargs = dict(fontsize=8, color=COLOR_MUTED, alpha=0.7, style="italic")
    ax.text(0.02, 0.97, "Contingency plan", ha="left", va="top", transform=ax.transAxes, **label_kwargs)
    ax.text(0.98, 0.97, "Critical - act now", ha="right", va="top", transform=ax.transAxes, **label_kwargs)
    ax.text(0.02, 0.03, "Low priority", ha="left", va="bottom", transform=ax.transAxes, **label_kwargs)
    ax.text(0.98, 0.03, "Monitor closely", ha="right", va="bottom", transform=ax.transAxes, **label_kwargs)

    for r in risks[:8]:
        prob = _LEVEL.get(str(r.get("probability", "medium")).lower(), 0.5)
        impact = _LEVEL.get(str(r.get("impact", "medium")).lower(), 0.5)
        desc = str(r.get("description", "") or r.get("risk_type", ""))[:40]
        critical = impact >= 0.8 and prob >= 0.7
        color = COLOR_LOW if critical else (COLOR_MID if impact >= 0.7 or prob >= 0.7 else COLOR_ACCENT)
        ax.scatter(prob, impact, s=160, c=color, alpha=0.75, edgecolor="white", linewidth=1.5, zorder=3)
        ax.annotate(desc, (prob, impact), textcoords="offset points", xytext=(8, 4), fontsize=8)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Probability  →", fontsize=9)
    ax.set_ylabel("Impact  →", fontsize=9)
    ax.set_title("Risk matrix", fontsize=11, fontweight="bold", pad=10)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(COLOR_GRID)

    return _fig_to_svg(fig)


# ---------------------------------------------------------------------------
# 5. Revenue Trajectory — conservative projection from SOM
# ---------------------------------------------------------------------------

def render_revenue_trajectory(data: dict[str, Any]) -> str | None:
    market = data.get("market") or {}
    som_y3 = _extract_amount_usd(market.get("som_y3"))
    if not som_y3:
        return None

    # Conservative S-curve: Month 6 → Year 5 as fraction of SOM_y3
    # (ramp up, exceed SOM_y3 by year 5 under optimistic retention)
    fractions = [0.01, 0.10, 0.40, 1.00, 1.55, 1.85]
    labels = ["Month 6", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"]
    values = [round(som_y3 * f, 2) for f in fractions]

    fig, ax = plt.subplots(figsize=(7.5, 4.0), dpi=110)
    ax.plot(labels, values, color=COLOR_ACCENT, linewidth=2.5, marker="o", markersize=6, markerfacecolor="white", markeredgewidth=2)
    ax.fill_between(labels, values, alpha=0.15, color=COLOR_ACCENT)

    for x, y in zip(labels, values):
        ax.annotate(_format_usd(y), (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)

    ax.set_ylabel("Revenue (USD millions)", fontsize=9)
    ax.set_title("Conservative revenue trajectory (anchored to SOM Y3)", fontsize=10, fontweight="bold", pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_GRID)
    ax.spines["bottom"].set_color(COLOR_GRID)
    ax.tick_params(colors=COLOR_MUTED)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4, color=COLOR_GRID)
    ax.set_axisbelow(True)
    return _fig_to_svg(fig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_color(score: int) -> str:
    if score >= 7:
        return COLOR_HIGH
    if score >= 5:
        return COLOR_MID
    return COLOR_LOW


def _extract_amount_usd(block: Any) -> float | None:
    """Normalise TAM/SAM/SOM blocks to millions-USD scalar."""
    if not isinstance(block, dict):
        return None
    value = block.get("value_usd")
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    unit = str(block.get("unit", "")).lower()
    if unit == "billion":
        return value * 1000.0
    # default assume millions
    return value


def _format_usd(millions: float) -> str:
    if millions >= 1000:
        return f"${millions/1000:.2f}B"
    if millions >= 1:
        return f"${millions:.1f}M"
    if millions > 0:
        return f"${millions*1000:.0f}K"
    return "—"


def _fig_to_svg(fig: Figure) -> str:
    """Export a matplotlib figure as a self-contained inline SVG string."""
    buf = io.StringIO()
    fig.tight_layout()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    svg = buf.getvalue()
    # Strip the XML declaration and DOCTYPE so it inlines cleanly in markdown/HTML
    svg = re.sub(r"<\?xml[^?]*\?>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
    return svg.strip()
