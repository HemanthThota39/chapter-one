# Chapter One — Data Model

> Postgres 16 · schema `public` · snake_case · UUIDs everywhere · timezone-aware timestamps (`timestamptz`).
> Migrations via Alembic. Hard-delete model throughout — no soft-delete columns.

---

## 1. Entity overview (ERD)

```
            ┌──────────┐
            │  users   │
            └────┬─────┘
    1 ───────────┤───────────────── 1
                 │                      ┌─────────────────────┐
                 │                      │  deletion_audit     │  (hashed user_id only)
                 │                      └─────────────────────┘
                 │
     ┌───────────┼───────────┬────────────┐
     │           │           │            │
     ▼           ▼           ▼            ▼
  ┌──────┐  ┌──────────┐  ┌──────┐   ┌──────────┐
  │fires │  │comments  │  │notif │   │analyses  │
  └──┬───┘  └────┬─────┘  └──┬───┘   └─────┬────┘
     │           │           │             │
     │           │           │             │────── analysis_events  (LISTEN/NOTIFY source)
     │           │           │             │────── agent_outputs    (raw per-agent JSON)
     │           │           │             │────── debate_turns
     │           │           │             │         │
     │           │           │             │         └── debate_patches (1:1 with turn, optional)
     │           │           │             │
     │           │           │             │────── report_versions
     │           │           │             │            │
     │           │           │             │            └── links to report_sections via section_ids
     │           │           │             │
     │           │           │             │────── report_sections (versioned)
     │           │           │             │
     │           │           │             └────── posts  (1:1 when visibility=public)
     │           │           │                       │
     │           ▼           ▼                       │
     │       post.id ◀─── comments, fires ───────────┘
     │
     └── fires.post_id ───── same
```

## 2. Tables (DDL)

### 2.1 `users`

```sql
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id         TEXT NOT NULL UNIQUE,    -- Google 'sub' via Entra
    email               TEXT NOT NULL UNIQUE,
    username            CITEXT NOT NULL UNIQUE,  -- case-insensitive unique
    display_name        TEXT NOT NULL,
    avatar_kind         TEXT NOT NULL CHECK (avatar_kind IN ('upload','library','initials')),
    avatar_url          TEXT,                    -- blob URL for upload/library; null for initials
    avatar_seed         TEXT,                    -- deterministic seed for 'initials'
    timezone            TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    default_visibility  TEXT NOT NULL DEFAULT 'public' CHECK (default_visibility IN ('public','private')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- denormalised stats (updated by triggers / workers; OK to be a few seconds stale)
    total_analyses      INTEGER NOT NULL DEFAULT 0,
    current_streak      INTEGER NOT NULL DEFAULT 0,
    longest_streak      INTEGER NOT NULL DEFAULT 0,
    fires_received      INTEGER NOT NULL DEFAULT 0,
    last_activity_date  DATE                     -- in user's timezone
);

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for future username fuzzy search
CREATE INDEX idx_users_username_trgm ON users USING GIN (username gin_trgm_ops);
```

**Rationale**:
- `username` is `CITEXT` so `Hemanth` == `hemanth` — prevents impersonation case variants
- `external_id` is the canonical identity anchor; email can theoretically change on the Google side
- Stats denormalised for cheap feed/profile reads; single source of truth still the transactional tables

### 2.2 `analyses`

```sql
CREATE TABLE analyses (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id                    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idea_text                   TEXT NOT NULL CHECK (char_length(idea_text) BETWEEN 20 AND 4000),
    idea_title                  TEXT,                      -- populated by orchestrator agent
    status                      TEXT NOT NULL CHECK (status IN ('queued','running','done','failed','cancelled')),
    visibility                  TEXT NOT NULL CHECK (visibility IN ('public','private')) DEFAULT 'public',
    slug                        TEXT,                      -- populated on publish, unique per owner
    current_report_version_id   UUID REFERENCES report_versions(id) DEFERRABLE INITIALLY DEFERRED,
    overall_score_100           INTEGER,                   -- latest version's score (cached)
    verdict                     TEXT,                      -- latest verdict (cached)
    confidence                  TEXT,                      -- HIGH/MEDIUM/LOW (cached)
    error_message               TEXT,
    submitted_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at                  TIMESTAMPTZ,
    completed_at                TIMESTAMPTZ,
    UNIQUE (owner_id, slug)
);

CREATE INDEX idx_analyses_owner_created       ON analyses (owner_id, submitted_at DESC);
CREATE INDEX idx_analyses_status_queued       ON analyses (status) WHERE status IN ('queued','running');
CREATE INDEX idx_analyses_public_recent       ON analyses (completed_at DESC) WHERE visibility = 'public' AND status = 'done';
```

**Cascade behaviour**: deleting a user deletes their analyses; deleting an analysis cascades to everything under it (versions, sections, debates, posts, events, outputs, PDFs, fires, comments).

### 2.3 `report_sections`

```sql
CREATE TABLE report_sections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id         UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    section_key         TEXT NOT NULL,            -- 'exec_summary', 'dim_1_problem', 'cvf_dashboard', etc.
    version_number      INTEGER NOT NULL,         -- monotonically increasing per (analysis, section_key)
    content_md          TEXT NOT NULL,            -- markdown (may contain inline SVG)
    structured_payload  JSONB,                    -- structured data for this section (e.g. scores, market figures)
    source_agents       TEXT[] NOT NULL,          -- e.g. ['problem_pmf']
    patch_turn_id       UUID REFERENCES debate_turns(id),  -- non-null if this section was created by an accepted patch
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (analysis_id, section_key, version_number)
);

CREATE INDEX idx_report_sections_analysis ON report_sections (analysis_id, section_key, version_number DESC);
```

**Rationale**: each section has an append-only version history. The `report_versions` table picks which section versions compose a given report version.

### 2.4 `report_versions`

```sql
CREATE TABLE report_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id         UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    version_number      INTEGER NOT NULL,
    section_ids         UUID[] NOT NULL,          -- array of report_sections.id composing this version
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          UUID REFERENCES users(id), -- null for the initial autogen version
    change_summary      TEXT,                     -- human-readable ("Accepted patch: updated Competitive Moat")
    overall_score_100   INTEGER,
    verdict             TEXT,
    UNIQUE (analysis_id, version_number)
);

CREATE INDEX idx_report_versions_analysis ON report_versions (analysis_id, version_number DESC);
```

### 2.5 `agent_outputs`

Raw JSON dumps from each agent — same as Phase 1's `raw/*.json` files, now in DB + Blob.

```sql
CREATE TABLE agent_outputs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id  UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    agent_name   TEXT NOT NULL,
    payload      JSONB NOT NULL,
    blob_path    TEXT,                  -- optional: full payload in Blob if too large for JSONB
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_outputs_analysis ON agent_outputs (analysis_id, agent_name);
```

### 2.6 `analysis_events`

Progress events for SSE. Worker writes, API reads via LISTEN.

```sql
CREATE TABLE analysis_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id  UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,         -- 'progress' | 'detail'
    stage        TEXT,
    percent      INTEGER,
    message      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analysis_events_analysis ON analysis_events (analysis_id, created_at);
```

**NOTIFY channel**: worker fires `pg_notify('analysis:' || analysis_id, '')` after each insert. API's LISTEN handler wakes and streams the new row.

### 2.7 `posts`

A Post exists when an analysis is public. 1:1 with `analyses` where `visibility='public'`. Separate table so feed queries stay fast.

```sql
CREATE TABLE posts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id      UUID NOT NULL UNIQUE REFERENCES analyses(id) ON DELETE CASCADE,
    owner_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    caption          TEXT CHECK (char_length(caption) <= 500),
    published_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fire_count       INTEGER NOT NULL DEFAULT 0,     -- denormalised
    comment_count    INTEGER NOT NULL DEFAULT 0      -- denormalised
);

CREATE INDEX idx_posts_published ON posts (published_at DESC);
```

### 2.8 `debate_turns`

```sql
CREATE TABLE debate_turns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    author_kind     TEXT NOT NULL CHECK (author_kind IN ('user','agent')),
    author_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,  -- null for agent turns
    content_md      TEXT NOT NULL,
    cited_urls      TEXT[] NOT NULL DEFAULT '{}',
    token_usage     JSONB,                 -- {input_tokens, output_tokens}
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_debate_turns_analysis ON debate_turns (analysis_id, created_at);
```

### 2.9 `debate_patches`

Proposed patches attached to a debate turn (not every turn has one).

```sql
CREATE TABLE debate_patches (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id                 UUID NOT NULL UNIQUE REFERENCES debate_turns(id) ON DELETE CASCADE,
    analysis_id             UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    target_section_key      TEXT NOT NULL,
    proposed_content_md     TEXT NOT NULL,
    proposed_structured     JSONB,
    rationale               TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','dismissed')),
    decided_by              UUID REFERENCES users(id) ON DELETE SET NULL,
    decided_at              TIMESTAMPTZ,
    resulting_version_id    UUID REFERENCES report_versions(id) ON DELETE SET NULL
);

CREATE INDEX idx_debate_patches_pending ON debate_patches (analysis_id, status) WHERE status = 'pending';
```

### 2.10 `comments`

```sql
CREATE TABLE comments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id      UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    author_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id    UUID REFERENCES comments(id) ON DELETE CASCADE,
    body         TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 1000),
    is_edited    BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted   BOOLEAN NOT NULL DEFAULT FALSE,   -- soft-delete for threading (body replaced with [deleted])
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at    TIMESTAMPTZ
);

CREATE INDEX idx_comments_post  ON comments (post_id, created_at);
CREATE INDEX idx_comments_parent ON comments (parent_id) WHERE parent_id IS NOT NULL;
```

**Note**: `is_deleted` exists here to preserve thread structure (if A replies to B and B is deleted, A's reply needs a parent). This is the ONLY soft-delete in the system. On user hard-delete, we do a hard DELETE on their comments — losing thread continuity is acceptable.

### 2.11 `fires`

```sql
CREATE TABLE fires (
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id      UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, post_id)
);
```

Primary key on `(user_id, post_id)` enforces one-fire-per-user-per-post. Toggling = DELETE + INSERT idempotent via upsert logic in code.

### 2.12 `notifications`

```sql
CREATE TABLE notifications (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,          -- 'fire' | 'comment' | 'reply' | 'debate_turn' | 'patch_pending' | 'streak_warning' | 'streak_broken' | 'analysis_done'
    payload      JSONB NOT NULL,         -- shape depends on kind
    read_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_unread ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX idx_notifications_user_all    ON notifications (user_id, created_at DESC);
CREATE INDEX idx_notifications_expiry      ON notifications (read_at) WHERE read_at IS NOT NULL;
```

**Auto-cleanup** (daily cron):
```sql
DELETE FROM notifications WHERE read_at IS NOT NULL AND read_at < NOW() - INTERVAL '30 days';
```

### 2.13 `deletion_audit`

```sql
CREATE TABLE deletion_audit (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id_hash         TEXT NOT NULL,         -- SHA-256 of deleted user.id
    assets_deleted       JSONB NOT NULL,        -- {analyses: 14, comments: 33, fires: 52, ...}
    deleted_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Hard-delete rows from this table after 30 days (a separate cron)
```

No PII. Exists solely so we can answer "did I actually delete that account when the user asked?".

## 3. Section keys — canonical list

Section keys are a closed enum used in `report_sections.section_key` and `debate_patches.target_section_key`:

```
exec_summary
cvf_dashboard
dim_1_problem
dim_2_market
dim_3_solution
dim_4_business_model
dim_5_moat
dim_6_timing
dim_7_gtm
dim_8_team
dim_9_traction
dim_10_risk
competitive_landscape
risk_matrix_chart
revenue_projection_chart
business_model_canvas
recommendations
sources
```

Full mapping to producing agents is in `02-architecture.md` §6.

## 4. Notification payload shapes

| `kind` | `payload` |
|---|---|
| `fire` | `{post_id, analysis_id, actor_id, actor_display_name}` |
| `comment` | `{post_id, analysis_id, comment_id, actor_id, actor_display_name, preview}` |
| `reply` | `{post_id, analysis_id, comment_id, parent_comment_id, actor_id, preview}` |
| `debate_turn` | `{analysis_id, turn_id, actor_id, preview}` |
| `patch_pending` | `{analysis_id, patch_id, target_section_key, proposed_by_actor_id}` |
| `streak_warning` | `{hours_remaining, current_streak}` |
| `streak_broken` | `{previous_streak, longest_streak}` |
| `analysis_done` | `{analysis_id, slug, verdict, overall_score_100}` |

## 5. Triggers & denormalisation

### Fires count on `posts`
```sql
CREATE FUNCTION fires_count_bump() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE posts SET fire_count = fire_count + 1 WHERE id = NEW.post_id;
    UPDATE users SET fires_received = fires_received + 1
      WHERE id = (SELECT owner_id FROM posts WHERE id = NEW.post_id);
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE posts SET fire_count = GREATEST(0, fire_count - 1) WHERE id = OLD.post_id;
    UPDATE users SET fires_received = GREATEST(0, fires_received - 1)
      WHERE id = (SELECT owner_id FROM posts WHERE id = OLD.post_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fires_count AFTER INSERT OR DELETE ON fires
  FOR EACH ROW EXECUTE FUNCTION fires_count_bump();
```

Similar triggers for `comments.post_id → posts.comment_count`.

### Streak maintenance
Not a trigger — runs in the Analysis Worker on status transition to `done`:
```python
def update_streak(user_id, completion_time_user_tz):
    today = completion_time_user_tz.date()
    last = user.last_activity_date
    if last == today:
        return  # already counted today
    if last and (today - last).days == 1:
        user.current_streak += 1
    else:
        user.current_streak = 1
    user.longest_streak = max(user.longest_streak, user.current_streak)
    user.last_activity_date = today
    user.total_analyses += 1
```

Cron job daily at each zone midnight scans for streaks that broke (no activity on yesterday) → zeroes `current_streak` and fires a `streak_broken` notification.

## 6. Indexes — full list

```sql
-- users
CREATE UNIQUE INDEX idx_users_external_id      ON users (external_id);
CREATE UNIQUE INDEX idx_users_email            ON users (email);
CREATE UNIQUE INDEX idx_users_username_ci      ON users (username);
CREATE INDEX        idx_users_username_trgm    ON users USING GIN (username gin_trgm_ops);

-- analyses
CREATE INDEX idx_analyses_owner_created        ON analyses (owner_id, submitted_at DESC);
CREATE INDEX idx_analyses_status_running       ON analyses (status) WHERE status IN ('queued','running');
CREATE INDEX idx_analyses_public_recent        ON analyses (completed_at DESC) WHERE visibility='public' AND status='done';
CREATE UNIQUE INDEX idx_analyses_owner_slug    ON analyses (owner_id, slug) WHERE slug IS NOT NULL;

-- report_sections / versions
CREATE INDEX idx_report_sections_analysis_kv   ON report_sections (analysis_id, section_key, version_number DESC);
CREATE INDEX idx_report_versions_analysis      ON report_versions (analysis_id, version_number DESC);

-- analysis_events
CREATE INDEX idx_analysis_events_analysis_ts   ON analysis_events (analysis_id, created_at);

-- posts
CREATE INDEX idx_posts_published               ON posts (published_at DESC);
CREATE INDEX idx_posts_owner                   ON posts (owner_id, published_at DESC);

-- comments
CREATE INDEX idx_comments_post_ts              ON comments (post_id, created_at);
CREATE INDEX idx_comments_parent               ON comments (parent_id) WHERE parent_id IS NOT NULL;

-- fires (already PK indexed)
CREATE INDEX idx_fires_post                    ON fires (post_id);

-- notifications
CREATE INDEX idx_notifications_user_unread     ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX idx_notifications_user_all        ON notifications (user_id, created_at DESC);
CREATE INDEX idx_notifications_expiry          ON notifications (read_at) WHERE read_at IS NOT NULL;

-- debate
CREATE INDEX idx_debate_turns_analysis_ts      ON debate_turns (analysis_id, created_at);
CREATE INDEX idx_debate_patches_pending        ON debate_patches (analysis_id, status) WHERE status='pending';
```

## 7. Migrations

- **Tooling**: Alembic + SQLAlchemy 2.x (async)
- **Location**: `backend/alembic/versions/`
- **Naming**: `YYYYMMDD_HHMM_<slug>.py` (e.g. `20260502_1430_add_debate_tables.py`)
- **Policy**: forward-only in prod; down migrations kept but not relied on
- **Baseline**: first migration creates the whole schema above
- **Zero-downtime rule**: schema changes that touch hot tables must be additive (nullable columns, new indexes with `CONCURRENTLY`); drops/renames happen in a multi-step deploy (new column → backfill → switch reads → drop old)

## 8. Hard-delete guarantees

When a user is deleted (`DELETE FROM users WHERE id = X`):

1. `ON DELETE CASCADE` propagates to: analyses, posts (via analysis), fires (direct), comments (direct), debate_turns (direct), notifications (direct), deletion_audit NOT affected (we keep it without PII)
2. Each analysis cascades further to: report_sections, report_versions, analysis_events, agent_outputs, debate_patches
3. Application code (inside transaction) deletes Blob assets: avatar, all PDFs for owner's analyses, all `agent_outputs.blob_path`, any orphan summary.md
4. Insert `deletion_audit` row with counts and hashed user_id

All within a single DB transaction. If blob deletion fails, the transaction still commits DB deletion and a background compactor retries blob deletes (eventual consistency on blob side).

## 9. Data retention

| Data | Retention |
|---|---|
| Users, analyses, reports, debates, posts, comments, fires | Forever, until user-initiated delete |
| Notifications (read) | 30 days after `read_at` |
| Notifications (unread) | Forever until read |
| `analysis_events` | 90 days after the analysis completed (logs only, replay-irrelevant after) |
| `agent_outputs` (raw JSON) | Forever (small rows; valuable for debugging + patch regen) |
| `deletion_audit` | 30 days (operations sanity only) |
| App Insights telemetry | 30 days (cost control) |
| Postgres automated backups | 7 days (Flexible Server default) |

## 10. Estimated row growth

Per analysis: ~1 analysis row, 18 section rows × N versions, 11 agent_output rows, ~80 analysis_event rows, optional 1 post row, optional debate rows.

At 5 users × 3 analyses/week × 52 weeks = 780 analyses/year ≈ **~15K sections, ~60K events/year**. Postgres Flexible Server Burstable B1ms handles this trivially.
