"""analyses core tables

Revision ID: 0003_analyses_core
Revises: 0002_username_nullable
Create Date: 2026-04-18 12:00:00 UTC

Introduces the full Phase 2 analysis data model:
  analyses, report_versions, report_sections,
  agent_outputs, analysis_events.

See docs/phase2/03-data-model.md §2.2-2.6 for rationale.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_analyses_core"
down_revision: Union[str, None] = "0002_username_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # analyses — top-level job table
    op.execute("""
        CREATE TABLE analyses (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id                    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            idea_text                   TEXT NOT NULL CHECK (char_length(idea_text) BETWEEN 20 AND 4000),
            idea_title                  TEXT,
            status                      TEXT NOT NULL CHECK (status IN ('queued','running','done','failed','cancelled')),
            visibility                  TEXT NOT NULL CHECK (visibility IN ('public','private')) DEFAULT 'public',
            slug                        TEXT,
            current_report_version_id   UUID,
            overall_score_100           INTEGER,
            verdict                     TEXT,
            confidence                  TEXT,
            error_message               TEXT,
            submitted_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at                  TIMESTAMPTZ,
            completed_at                TIMESTAMPTZ,
            UNIQUE (owner_id, slug)
        );
    """)
    op.execute("CREATE INDEX idx_analyses_owner_created ON analyses (owner_id, submitted_at DESC);")
    op.execute("CREATE INDEX idx_analyses_status_running ON analyses (status) WHERE status IN ('queued','running');")
    op.execute("CREATE INDEX idx_analyses_public_recent ON analyses (completed_at DESC) WHERE visibility='public' AND status='done';")

    # report_sections — append-only per-(analysis, section_key) version history
    op.execute("""
        CREATE TABLE report_sections (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id         UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            section_key         TEXT NOT NULL,
            version_number      INTEGER NOT NULL,
            content_md          TEXT NOT NULL,
            structured_payload  JSONB,
            source_agents       TEXT[] NOT NULL,
            patch_turn_id       UUID,  -- FK added in M4 when debate_turns exists
            generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (analysis_id, section_key, version_number)
        );
    """)
    op.execute("CREATE INDEX idx_report_sections_akv ON report_sections (analysis_id, section_key, version_number DESC);")

    # report_versions — each version = a snapshot referencing a set of section ids
    op.execute("""
        CREATE TABLE report_versions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id         UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            version_number      INTEGER NOT NULL,
            section_ids         UUID[] NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
            change_summary      TEXT,
            overall_score_100   INTEGER,
            verdict             TEXT,
            UNIQUE (analysis_id, version_number)
        );
    """)
    op.execute("CREATE INDEX idx_report_versions_analysis ON report_versions (analysis_id, version_number DESC);")

    # Back-fill the FK analyses.current_report_version_id -> report_versions(id)
    op.execute("""
        ALTER TABLE analyses
            ADD CONSTRAINT fk_analyses_current_version
            FOREIGN KEY (current_report_version_id)
            REFERENCES report_versions(id)
            DEFERRABLE INITIALLY DEFERRED;
    """)

    # agent_outputs — raw JSON dumps from each pipeline agent
    op.execute("""
        CREATE TABLE agent_outputs (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id  UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            agent_name   TEXT NOT NULL,
            payload      JSONB NOT NULL,
            blob_path    TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_agent_outputs_analysis ON agent_outputs (analysis_id, agent_name);")

    # analysis_events — progress events for SSE (LISTEN/NOTIFY-driven)
    op.execute("""
        CREATE TABLE analysis_events (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id  UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            kind         TEXT NOT NULL,
            stage        TEXT,
            percent      INTEGER,
            message      TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_analysis_events_analysis ON analysis_events (analysis_id, created_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analysis_events;")
    op.execute("DROP TABLE IF EXISTS agent_outputs;")
    op.execute("ALTER TABLE analyses DROP CONSTRAINT IF EXISTS fk_analyses_current_version;")
    op.execute("DROP TABLE IF EXISTS report_versions;")
    op.execute("DROP TABLE IF EXISTS report_sections;")
    op.execute("DROP TABLE IF EXISTS analyses;")
