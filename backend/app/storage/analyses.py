"""Persistence layer for the Phase 2 analysis pipeline.

All DB writes go through here. Uses asyncpg directly (no ORM).
NOTIFY channels used to drive SSE streaming to the API replicas.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from app.db import transaction

log = logging.getLogger(__name__)

SECTION_ORDER = [
    "executive_summary",
    "cvf_dashboard",
    "dim_1_problem",
    "dim_2_market",
    "dim_3_solution",
    "dim_4_business_model",
    "dim_5_moat",
    "dim_6_timing",
    "dim_7_gtm",
    "dim_8_team",
    "dim_9_traction",
    "dim_10_risk",
    "competitive_landscape",
    "risk_matrix_chart",
    "revenue_projection_chart",
    "business_model_canvas",
    "recommendations",
    "sources",
]


@dataclass
class SectionInput:
    section_key: str
    content_md: str
    source_agents: list[str]
    structured_payload: dict[str, Any] | None = None


def _notify_channel(analysis_id: str) -> str:
    """Postgres channel names must match /^[a-zA-Z_][a-zA-Z0-9_]*$/."""
    return f"analysis_{str(analysis_id).replace('-', '_')}"


# ---------------------------------------------------------------------
# Analysis row lifecycle
# ---------------------------------------------------------------------

async def create_analysis(*, owner_id: str, idea_text: str, visibility: str = "public") -> str:
    async with transaction() as conn:
        row = await conn.fetchrow(
            """INSERT INTO analyses (owner_id, idea_text, status, visibility)
                    VALUES ($1::uuid, $2, 'queued', $3)
                 RETURNING id""",
            owner_id, idea_text, visibility,
        )
    return str(row["id"])


async def mark_running(analysis_id: str) -> None:
    async with transaction() as conn:
        await conn.execute(
            "UPDATE analyses SET status='running', started_at=NOW() WHERE id=$1::uuid AND status='queued'",
            analysis_id,
        )


async def mark_failed(analysis_id: str, error_message: str) -> None:
    async with transaction() as conn:
        await conn.execute(
            """UPDATE analyses
                  SET status='failed',
                      completed_at=NOW(),
                      error_message=$2
                WHERE id=$1::uuid""",
            analysis_id, error_message[:2000],
        )


async def mark_done(
    analysis_id: str, *,
    idea_title: str | None,
    overall_score_100: int | None,
    verdict: str | None,
    confidence: str | None,
    slug: str | None,
    current_version_id: str,
) -> None:
    async with transaction() as conn:
        await conn.execute(
            """UPDATE analyses
                  SET status='done',
                      completed_at=NOW(),
                      idea_title=$2,
                      overall_score_100=$3,
                      verdict=$4,
                      confidence=$5,
                      slug=$6,
                      current_report_version_id=$7::uuid
                WHERE id=$1::uuid""",
            analysis_id, idea_title, overall_score_100, verdict, confidence, slug, current_version_id,
        )


async def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    async with transaction() as conn:
        row = await conn.fetchrow(
            """SELECT a.id, a.owner_id, a.idea_text, a.idea_title, a.status,
                      a.visibility, a.slug, a.overall_score_100, a.verdict, a.confidence,
                      a.submitted_at, a.started_at, a.completed_at, a.error_message,
                      a.current_report_version_id,
                      u.username AS owner_username, u.display_name AS owner_display_name,
                      u.avatar_url AS owner_avatar_url
                 FROM analyses a
                 JOIN users u ON u.id = a.owner_id
                WHERE a.id = $1::uuid""",
            analysis_id,
        )
    return dict(row) if row else None


async def list_user_analyses(owner_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    async with transaction() as conn:
        rows = await conn.fetch(
            """SELECT id, idea_title, status, visibility, overall_score_100, verdict,
                      confidence, submitted_at, completed_at
                 FROM analyses
                WHERE owner_id = $1::uuid
             ORDER BY submitted_at DESC
                LIMIT $2""",
            owner_id, limit,
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Progress events + NOTIFY
# ---------------------------------------------------------------------

async def publish_event(
    analysis_id: str,
    *,
    kind: str,
    stage: str | None = None,
    percent: int | None = None,
    message: str | None = None,
) -> None:
    """Insert an event row and fire NOTIFY so the SSE endpoint wakes."""
    async with transaction() as conn:
        await conn.execute(
            """INSERT INTO analysis_events (analysis_id, kind, stage, percent, message)
                    VALUES ($1::uuid, $2, $3, $4, $5)""",
            analysis_id, kind, stage, percent, message,
        )
        payload = json.dumps({"kind": kind, "stage": stage, "percent": percent, "message": message})
        # Payload is capped at 8000 bytes by Postgres NOTIFY
        await conn.execute(f"NOTIFY {_notify_channel(analysis_id)}, '{payload.replace(chr(39), chr(39)*2)[:7900]}'")


async def fetch_past_events(analysis_id: str, after_id: str | None = None) -> list[dict[str, Any]]:
    """Replay events for an SSE reconnect. after_id is an ISO timestamp string."""
    if after_id:
        async with transaction() as conn:
            rows = await conn.fetch(
                """SELECT id, kind, stage, percent, message, created_at
                     FROM analysis_events
                    WHERE analysis_id=$1::uuid AND created_at > $2::timestamptz
                 ORDER BY created_at ASC""",
                analysis_id, after_id,
            )
    else:
        async with transaction() as conn:
            rows = await conn.fetch(
                """SELECT id, kind, stage, percent, message, created_at
                     FROM analysis_events
                    WHERE analysis_id=$1::uuid
                 ORDER BY created_at ASC""",
                analysis_id,
            )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Report storage — sections + versions
# ---------------------------------------------------------------------

async def save_initial_version(
    analysis_id: str,
    sections: list[SectionInput],
    *,
    overall_score_100: int | None,
    verdict: str | None,
) -> str:
    """Write initial v1 of the report — all section rows at version_number=1
    and a report_versions row pointing to them. Returns version id."""
    async with transaction() as conn:
        section_ids: list[str] = []
        for s in sections:
            row = await conn.fetchrow(
                """INSERT INTO report_sections
                     (analysis_id, section_key, version_number, content_md,
                      structured_payload, source_agents)
                   VALUES ($1::uuid, $2, 1, $3, $4::jsonb, $5)
                RETURNING id""",
                analysis_id,
                s.section_key,
                s.content_md,
                json.dumps(s.structured_payload, default=str) if s.structured_payload else None,
                s.source_agents,
            )
            section_ids.append(str(row["id"]))

        version_row = await conn.fetchrow(
            """INSERT INTO report_versions
                 (analysis_id, version_number, section_ids,
                  change_summary, overall_score_100, verdict)
               VALUES ($1::uuid, 1, $2::uuid[], $3, $4, $5)
            RETURNING id""",
            analysis_id, section_ids, "Initial analysis", overall_score_100, verdict,
        )
    return str(version_row["id"])


async def render_report_markdown(analysis_id: str, *, version_id: str | None = None) -> str | None:
    """Compose the full report markdown by concatenating sections of the given
    (or current) version in canonical order."""
    async with transaction() as conn:
        if version_id is None:
            row = await conn.fetchrow(
                "SELECT current_report_version_id FROM analyses WHERE id=$1::uuid",
                analysis_id,
            )
            if not row or not row["current_report_version_id"]:
                return None
            version_id = str(row["current_report_version_id"])

        version = await conn.fetchrow(
            "SELECT section_ids FROM report_versions WHERE id=$1::uuid",
            version_id,
        )
        if not version:
            return None
        sections = await conn.fetch(
            """SELECT section_key, content_md
                 FROM report_sections
                WHERE id = ANY($1::uuid[])""",
            list(version["section_ids"]),
        )

    by_key = {s["section_key"]: s["content_md"] for s in sections}
    ordered: list[str] = []
    for key in SECTION_ORDER:
        md = by_key.get(key)
        if md:
            ordered.append(md)
    for key, md in by_key.items():
        if key not in SECTION_ORDER:
            ordered.append(md)  # preserve any unexpected keys at the end
    return "\n\n".join(ordered)


# ---------------------------------------------------------------------
# Per-agent raw JSON dumps
# ---------------------------------------------------------------------

async def save_agent_output(
    analysis_id: str, agent_name: str, payload: dict[str, Any], blob_path: str | None = None,
) -> None:
    async with transaction() as conn:
        await conn.execute(
            """INSERT INTO agent_outputs (analysis_id, agent_name, payload, blob_path)
                    VALUES ($1::uuid, $2, $3::jsonb, $4)""",
            analysis_id, agent_name, json.dumps(payload, default=str), blob_path,
        )


# ---------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------

def slugify(title: str, max_words: int = 8) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())[:max_words]
    slug = "-".join(words) or "analysis"
    return slug[:80]


async def next_free_slug(owner_id: str, base: str) -> str:
    async with transaction() as conn:
        existing = await conn.fetch(
            "SELECT slug FROM analyses WHERE owner_id=$1::uuid AND slug LIKE $2",
            owner_id, f"{base}%",
        )
    used = {r["slug"] for r in existing if r["slug"]}
    if base not in used:
        return base
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    return f"{base}-{i}"
