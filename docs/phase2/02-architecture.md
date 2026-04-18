# Chapter One — Phase 2 Architecture

> Target state. Covers system context, container decomposition, runtime flows, data flow, and the subtle bits (section regeneration, debate grounding, SSE reconnection).
>
> **Style**: C4 model, ASCII diagrams (portable). Mermaid deliberately not used — we want these docs to render correctly in GitHub, VS Code, IDE previews, and `cat`.

---

## 1. System context

```
                              ┌───────────────────┐
                              │                   │
                              │   Google OIDC     │
                              │                   │
                              └────────▲──────────┘
                                       │ federation
                                       │
  ┌──────────┐      ┌───────────────┐  │
  │          │      │               │  │
  │  User    │◀────▶│  Chapter One  │──┘
  │ (browser)│      │     SaaS      │
  │          │      │               │◀──────── Azure AI Foundry
  └──────────┘      └──────┬────────┘           (gpt-5.3-chat + web_search)
        ▲                  │
        │ PDF download     │ 
        │ Share URL        ▼
        │           ┌─────────────┐
        └───────────│  Azure Blob │  (public objects: PDFs, avatars)
                    └─────────────┘
```

- **User** interacts via any browser; desktop and mobile
- **Chapter One SaaS** is the product itself (full Azure-hosted)
- **Google OIDC** via Entra External ID federation — the only IdP
- **Azure AI Foundry** provides LLM + web search; called from the backend
- **Azure Blob** also serves selected public content (PDFs, avatars) directly via signed URLs to reduce backend load

## 2. Container view (C4 level 2)

```
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                         Chapter One SaaS                                │
    │                                                                         │
    │  ┌───────────────────┐    HTTPS      ┌──────────────────────────────┐  │
    │  │                   │ ◀───────────▶ │                              │  │
    │  │  Static Web App   │               │  Backend API                 │  │
    │  │  (Next.js 15)     │  SSE          │  (FastAPI, Container App)    │  │
    │  │                   │ ◀───────────  │                              │  │
    │  └───────────────────┘               │   ┌────────────────────┐     │  │
    │                                      │   │  Auth middleware   │     │  │
    │                                      │   │  (Entra JWT verify)│     │  │
    │                                      │   └────────────────────┘     │  │
    │                                      └──────┬──────┬──────┬─────────┘  │
    │                                             │      │      │            │
    │                                             │      │      │            │
    │                                             ▼      ▼      ▼            │
    │                             ┌──────────┐┌──────┐┌──────────┐┌────────┐ │
    │                             │          ││      ││          ││        │ │
    │                             │ Postgres ││ Blob ││ Service  ││ Key    │ │
    │                             │ Flexible ││      ││ Bus      ││ Vault  │ │
    │                             │ Server   ││      ││          ││        │ │
    │                             │          ││      ││          ││        │ │
    │                             └──────────┘└──────┘└─────┬────┘└────────┘ │
    │                                                       │                │
    │                                                       │ dequeue        │
    │                                                       ▼                │
    │                                      ┌──────────────────────────────┐  │
    │                                      │                              │  │
    │                                      │  Analysis Worker             │  │
    │                                      │  (FastAPI agents,            │  │
    │                                      │   Container App Job)         │  │
    │                                      │                              │  │
    │                                      └──────┬───────────────────────┘  │
    │                                             │                          │
    │                                             │ writes + NOTIFY          │
    │                                             ▼                          │
    │                                    [same Postgres + Blob]              │
    │                                                                         │
    │  ┌──────────────────────────────┐                                      │
    │  │                              │                                      │
    │  │  PDF Renderer Worker         │── Playwright headless Chromium       │
    │  │  (Container App Job,         │                                      │
    │  │   on-demand)                 │                                      │
    │  │                              │                                      │
    │  └──────────────────────────────┘                                      │
    │                                                                         │
    │  ┌──────────────────────────────┐                                      │
    │  │                              │                                      │
    │  │  Cron Worker                 │   daily: notif expiry, streak recalc │
    │  │  (Container App Job,         │                                      │
    │  │   scheduled)                 │                                      │
    │  │                              │                                      │
    │  └──────────────────────────────┘                                      │
    │                                                                         │
    │                       + Log Analytics / App Insights for all           │
    └─────────────────────────────────────────────────────────────────────────┘
```

### Container inventory

| Container | Runtime | Purpose |
|---|---|---|
| **Static Web App** | Azure SWA (managed) | Next.js frontend + CDN + auth redirect glue |
| **Backend API** | Container App (always-on, 1-3 replicas) | HTTP + SSE endpoints, auth, short synchronous ops |
| **Analysis Worker** | Container App Job (queue-triggered) | Runs the multi-query research + analysis + scoring + compile pipeline |
| **PDF Renderer** | Container App Job (HTTP-triggered via backend) | Launches Playwright, renders report HTML → PDF → Blob |
| **Cron Worker** | Container App Job (scheduled) | Notification expiry, streak recalculation, blob GC |
| **Postgres** | Flexible Server Burstable B1ms | All relational data |
| **Blob Storage** | Standard LRS, hot tier | PDFs, avatars, per-agent raw JSON, per-analysis summary.md |
| **Service Bus** | Standard tier | Analysis job queue (`analyses.submitted`), plus future topics |
| **Key Vault** | Standard | API keys, DB password, OAuth secrets |
| **Log Analytics + App Insights** | Pay-as-you-go | Logs, traces, alerts |

## 3. Technology choices (concise — full rationale in `10-decisions.md`)

- **Backend**: Python 3.12 + FastAPI (inherited from Phase 1, unchanged)
- **Frontend**: Next.js 15 App Router, Tailwind, shadcn-style primitives
- **Auth**: Entra External ID — Google social login only at launch
- **DB**: PostgreSQL 16 Flexible Server, Burstable B1ms
- **Queue**: Azure Service Bus — Standard tier (supports topics for future fan-out)
- **Async progress**: Postgres `LISTEN/NOTIFY` + SSE (no SignalR in Phase 2)
- **PDF**: Playwright headless Chromium in a dedicated Container App Job
- **Charts**: server-rendered SVG (matplotlib), inherited from Phase 1
- **Observability**: App Insights for telemetry + Azure Monitor alerts
- **IaC**: Bicep (Azure-native, first-class tooling)
- **CI/CD**: GitHub Actions → Azure Container Registry → Container Apps; SWA has native GitHub integration for the frontend

## 4. Key runtime flows

### 4.1 Submit and run an analysis

```
[Browser]                [API]              [Service Bus]      [Worker Job]        [Postgres]        [Blob]
   │                       │                     │                  │                   │                │
   ├── POST /api/analyses ─▶│                    │                  │                   │                │
   │                       ├── INSERT analyses ─────────────────────▶                   │                │
   │                       │  (status=queued)    │                  │                   │                │
   │                       ├── ENQUEUE msg ─────▶                   │                   │                │
   │                       │                     │                  │                   │                │
   │ ◀── 202 {analysis_id} ┤                     │                  │                   │                │
   │                       │                     │                  │                   │                │
   ├── GET /stream (SSE) ──▶│                    │                  │                   │                │
   │                       ├── LISTEN notify ────────────────────────────────────────▶  │                │
   │                       │                     │                  │                   │                │
   │                       │                     ├── deliver msg ──▶│                   │                │
   │                       │                     │                  ├── run pipeline... │                │
   │                       │                     │                  ├── write progress ─▶│               │
   │                       │                     │                  │  + NOTIFY ch      │                │
   │                       │ ◀─── NOTIFY ────────────────────────────────────────────────┤               │
   │◀── SSE: progress ─────┤                     │                  │                   │                │
   │                       │                     │                  ├── write agent raw JSON ─────────▶  │
   │                       │                     │                  ├── ... repeat ...  │                │
   │                       │                     │                  ├── render SVG charts─────────────▶  │
   │                       │                     │                  ├── INSERT sections ▶│               │
   │                       │                     │                  │  + report_versions│                │
   │                       │                     │                  ├── UPDATE status=done + NOTIFY      │
   │                       │ ◀─── NOTIFY ────────────────────────────────────────────────┤               │
   │◀── SSE: done ─────────┤                     │                  │                   │                │
   │                       │                     │                  │                   │                │
```

Key properties:
- Worker is idempotent on `analysis_id` — re-delivery is safe (dead-letter after 3 retries)
- Postgres `LISTEN/NOTIFY` on channel `analysis:{id}` for SSE fan-out; on SSE connect we also SELECT the past N events (replay) before streaming
- If the API pod restarts mid-SSE, client reconnects → replay from DB → catch up → stream live

### 4.2 Debate turn → accepted patch → new version

```
[User]            [API]                [LLM Agent]           [Postgres]           [Debate section-regen]
  │                 │                      │                     │                        │
  ├── POST turn ──▶ │                      │                     │                        │
  │                 ├── INSERT debate_turn (pending) ────────────▶                        │
  │                 ├── build context: saved research + latest report + thread ──▶        │
  │                 ├── agent.chat_json with web_search enabled ──▶                       │
  │                 │                      │                     │                        │
  │                 │ ◀── {reply_md, citations, proposes_patch?} ┤                        │
  │                 │                      │                     │                        │
  │                 ├── UPDATE debate_turn (content, citations, proposed_patch) ──▶       │
  │ ◀── 200 ────────┤                      │                     │                        │
  │                 │                      │                     │                        │
  │                 │                      │                     │                        │
  ├── POST patch/accept (owner only) ──▶  │                     │                        │
  │                 ├── load target section + deps ──────────────▶                        │
  │                 ├── dispatch section-regen ───────────────────────────────────────▶   │
  │                 │                      │                     │                        ├── rerun affected
  │                 │                      │                     │                        │    agents with
  │                 │                      │                     │                        │    debate context
  │                 │                      │                     │                        │
  │                 │                      │                     │   ◀── write new       │
  │                 │                      │                     │       section_versions ┤
  │                 │                      │                     │   ◀── new report_version
  │                 │                      │                     │                        │
  │ ◀── 200 {new_version_id} ──────────────────────────────────────────────────────────── ┤
```

Section-regen rules:
- **Direct**: regenerate the section the patch targets
- **Dependents** (auto-detected from scoring inputs):
  - Any dimension score change → regenerate scoring + executive summary + recommendations
  - Market size change → regenerate revenue trajectory chart data
  - Competitor change → regenerate competitive landscape card + recommendations
- Other sections untouched (saves tokens, speeds up accept)

### 4.3 Public share link access

```
[Unauthenticated user]                  [API]                  [Postgres]               [Blob]
        │                                 │                         │                       │
        ├── GET /{user}/reports/{slug} ──▶│                         │                       │
        │                                 ├── resolve to analysis_id▶                       │
        │                                 │                         │                       │
        │                                 │ ◀── {visibility, owner, current_version} ───────┤
        │                                 │                         │                       │
        │                                 │   is public?            │                       │
        │                                 │ ─────── YES ──┐         │                       │
        │                                 │               │         │                       │
        │                                 ├── assemble markdown from section versions ──────▶│
        │                                 │               │         │                       │
        │                                 │               │ ◀── section contents ───────────┤
        │ ◀── full report HTML ───────────┤               │         │                       │
        │                                 │               │         │                       │
        │                                 │ ─────── NO ───┤         │                       │
        │                                 │               │         │                       │
        │ ◀── 302 /login?next=... ────────┤                         │                       │
```

## 5. Data flow — section storage model

A report is not one big markdown blob anymore. It's a set of versioned sections:

```
                     ┌────────────────────────────────────┐
                     │  analyses                          │
                     │  - id                              │
                     │  - owner_id                        │
                     │  - idea_text                       │
                     │  - status                          │
                     │  - current_report_version_id  ───┐ │
                     │  - created_at                    │ │
                     └──────────────────────────────────│─┘
                                                        │
                                                        │
                                      ┌─────────────────▼───────────────┐
                                      │  report_versions                │
                                      │  - id                           │
                                      │  - analysis_id (fk)             │
                                      │  - version_number               │
                                      │  - created_at                   │
                                      │  - created_by                   │
                                      │  - change_summary               │
                                      │  - section_ids []  ─────────────┐
                                      │  - overall_score                │
                                      │  - verdict                      │
                                      └─────────────────────────────────┘
                                                                        │
                                                                        ▼
                                      ┌─────────────────────────────────┐
                                      │  report_sections                │
                                      │  - id                           │
                                      │  - analysis_id (fk)             │
                                      │  - section_key (dimension_1,    │
                                      │                 exec_summary,   │
                                      │                 ...)            │
                                      │  - version_number               │
                                      │  - content_md                   │
                                      │  - source_agents []             │
                                      │  - generated_at                 │
                                      │  - patch_turn_id nullable (fk   │
                                      │    to debate_turn that caused)  │
                                      └─────────────────────────────────┘
```

To render a report:
1. Load `analyses.current_report_version_id`
2. Load `report_versions.section_ids`
3. Load those `report_sections` rows
4. Concatenate `content_md` in the canonical section order → full markdown
5. Add live SVG charts from the structured data (scoring, market, etc. denormalised onto the version row for chart rendering)
6. Serve

## 6. Section → agent mapping (Phase 2)

| Section key | Source agent(s) | Depends on |
|---|---|---|
| `executive_summary` | report_compiler | all others |
| `cvf_dashboard` | scoring (chart + table) | all dimensions |
| `dim_1_problem` | problem_pmf | research (market, competitors, timing) |
| `dim_2_market` | business_model (market portion) | market_sizing |
| `dim_3_solution` | problem_pmf | research (market, competitors) |
| `dim_4_business_model` | business_model | market_sizing |
| `dim_5_moat` | risk_moat | competitive_intel |
| `dim_6_timing` | business_model (timing portion) | news_trends |
| `dim_7_gtm` | gtm_team | competitive_intel |
| `dim_8_team` | gtm_team | - |
| `dim_9_traction` | risk_moat | news_trends, competitive_intel |
| `dim_10_risk` | risk_moat | regulatory, competitive_intel |
| `competitive_landscape` | competitive_intel + gtm_team | - |
| `risk_matrix_chart` | risk_moat | - |
| `revenue_projection_chart` | business_model (derived) | market_sizing |
| `business_model_canvas` | report_compiler | business_model, gtm_team |
| `recommendations` | scoring + report_compiler | all scoring outputs |
| `sources` | aggregator (not an LLM call) | all research agents |

On patch accept:
- Direct section → rerun its `source_agents` with `debate_context` added
- Inverse index (depends_on) drives downstream regen
- `sources` always re-aggregates (cheap, no LLM)

## 7. Debate grounding pipeline

Each debate turn goes through:

1. **Retrieval**: load the stored research bundle (`agent_outputs` table for this analysis) → top-K snippets relevant to the user's turn via cheap keyword scoring (no embeddings in Phase 2)
2. **Live search**: if the turn mentions specific entities/figures not in stored research → run `web_search` via Responses API with that query
3. **Generation**: LLM call with:
   - Report summary + affected section markdown
   - Relevant research snippets (retrieved)
   - Live search results (if any)
   - Debate thread history (last N turns)
   - User's current turn
   - System prompt: "Neutral + evidence-bound + cite every claim + say I-don't-know when appropriate"
4. **Patch detection**: structured output includes optional `proposes_patch: {target_section_id, new_content, rationale}`
5. **Persist**: turn + citations + patch stored; SSE event pushed to all subscribed viewers

## 8. Repository layout (monorepo)

```
chapter-one/
├── backend/                     # FastAPI + agents (inherited from Phase 1)
│   ├── app/
│   │   ├── api/                 # HTTP routes (existing + new: /auth, /comments, /debate, /notifications, /users)
│   │   ├── core/                # LLM client, charts, progress, mermaid sanitizer (retained as defence)
│   │   ├── agents/              # pipeline agents
│   │   ├── debate/              # NEW: debate engine, section-regen orchestrator
│   │   ├── models/              # Pydantic + SQLAlchemy models
│   │   ├── storage/             # Postgres, Blob, Service Bus clients
│   │   ├── observability/       # structured logging (now App Insights adapter)
│   │   ├── auth/                # NEW: Entra token validation
│   │   └── workers/             # NEW: worker entrypoints (analysis, pdf, cron)
│   ├── alembic/                 # DB migrations
│   ├── pyproject.toml
│   └── tests/
├── frontend/                    # Next.js 15 App Router
│   ├── app/
│   │   ├── (marketing)/         # landing page (logged-out)
│   │   ├── (auth)/              # onboarding, login callback
│   │   ├── (app)/               # authenticated app: feed, /me/*, profile, report, debate
│   │   └── api/auth/            # NextAuth OIDC callback
│   ├── components/
│   ├── lib/
│   └── package.json
├── infra/                       # Bicep modules + GitHub Actions workflows
│   ├── main.bicep               # top-level deployment
│   ├── modules/
│   │   ├── container-app.bicep
│   │   ├── postgres.bicep
│   │   ├── storage.bicep
│   │   ├── service-bus.bicep
│   │   ├── key-vault.bicep
│   │   ├── monitor.bicep
│   │   └── entra-external-id.bicep
│   └── envs/
│       ├── dev.parameters.json
│       └── prod.parameters.json
├── docs/
│   └── phase2/                  # this documentation tree
├── .github/
│   └── workflows/
│       ├── backend-ci.yml       # lint + test on every push/PR
│       ├── frontend-ci.yml
│       ├── deploy-dev.yml       # auto-deploy main → dev env
│       └── deploy-prod.yml      # tag-triggered → prod env
├── README.md
├── LICENSE                      # MIT
└── CONTRIBUTING.md              # contribution guidelines for future friends
```

## 9. Environments

| Env | Purpose | Region | SKUs | Domain |
|---|---|---|---|---|
| **dev** | Developer sandbox + PR previews | Central India | Container App consumption, Postgres Burstable B1ms, Blob LRS, Service Bus Basic | `dev.<...>.azurestaticapps.net` |
| **prod** | Public product | Central India | Same SKUs but with always-on min replica=1 | `<...>.azurestaticapps.net` (custom domain deferred) |

Strategy:
- **dev auto-deploys from `main`** after CI green
- **prod deploys on tag push** (`v*`) — manual promotion with changelog review
- Separate Azure Entra External ID tenants per env (clean user boundaries)
- Separate Service Bus namespaces, Postgres instances, Blob accounts per env

## 10. Scaling posture (for later)

Phase 2 launches with fixed-scale containers, since 5 users. The architecture supports:
- **Horizontal**: Container Apps scale on HTTP concurrency; worker jobs scale on Service Bus queue depth
- **Read-scaling**: Postgres read replicas (Phase 3)
- **Fan-out to many SSE clients**: migrate from Postgres NOTIFY to SignalR if concurrent SSE exceeds ~50 (currently handles fine up to hundreds in benchmarks)
- **Global read-latency**: Azure Front Door + multi-region blob replication (Phase 4)

None of this is built in Phase 2. The point is: nothing in the Phase 2 design prevents it.
