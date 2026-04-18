# Chapter One — Architecture Decision Records

> Each ADR captures: Context · Decision · Consequences · Trigger-for-revisit.
> Kept in one file because there are <50 of them. Phase 3+ will split by number.

---

## ADR-001 — Backend stack: Python 3.12 + FastAPI

**Context**: Phase 1 is already Python/FastAPI. Changing stack mid-project is expensive; no compelling benefit.
**Decision**: Keep Python 3.12 + FastAPI for all backend services (API, workers, jobs).
**Consequences**: Reuse all Phase 1 pipeline code, prompt library, chart generator, observability. SQLAlchemy + alembic added for DB migrations.
**Revisit**: If >80% of backend surface is LLM + async I/O, could swap to TypeScript/Bun for simpler auth story. Not now.

---

## ADR-002 — Frontend stack: Next.js 15 App Router

**Context**: Phase 1 uses Next.js 15. Already handles SSE, markdown rendering, inline SVG (via rehype-raw).
**Decision**: Stay on Next.js 15 App Router. Migrate to Static Web Apps hosting.
**Consequences**: Use SWA's native GitHub integration for CI/CD. Server components for SEO on share links. Client components for interactive bits (debate panel, feed).
**Revisit**: Not expected.

---

## ADR-003 — LLM: `gpt-5.3-chat` on Azure AI Foundry

**Context**: Phase 1 validated this model + Azure AI Foundry web_search combo.
**Decision**: Keep it. Existing resource `testingclaudecode.cognitiveservices.azure.com` reused.
**Consequences**: Cross-region call from Central India → East US 2 (or wherever the Foundry resource lives). Adds ~60ms per call. Acceptable.
**Revisit**: If Azure adds `gpt-5.3-chat` in Central India, migrate. If cost becomes prohibitive, consider cheaper fallback models for non-critical agents (e.g. orchestrator).

---

## ADR-004 — Web search provider

**Context**: Azure's web_search tool = Bing-backed. User preference is Google but declined to pay for Serper/Google CSE.
**Decision**: Azure web_search tool for Phase 2. Deferred Serper.dev integration as Phase 3 improvement behind a search-provider abstraction.
**Consequences**: Accept Bing quality; rely on multi-query engine to compensate.
**Revisit**: When user count >10 or when a specific query type consistently produces poor results.

---

## ADR-005 — Identity: Entra External ID + Google social login only

**Context**: Low-friction login required. Everyone has Google.
**Decision**: **Entra External ID** (Azure-native, free 50K MAU). Google as sole social IdP at launch.
**Consequences**: One vendor lock (Azure) matches "all in Azure" stance. No email/password to worry about. Adding Apple/Microsoft/GitHub is config-only later.
**Revisit**: If Google OIDC federation has unplanned regional issues, evaluate Auth.js with multiple IdPs.

---

## ADR-006 — Compute: Container Apps + Static Web Apps

**Context**: Candidates evaluated: App Service (simple but opinionated), AKS (overkill), Functions (cold starts hurt 3-min analyses), Container Apps (goldilocks).
**Decision**:
- **Backend API** → Azure Container Apps (always-on, 1 replica in dev, 1-3 replicas in prod with HTTP-concurrency scaling)
- **Analysis Worker** → Container Apps Job (queue-triggered)
- **PDF Renderer** → Container Apps Job (event-triggered from backend)
- **Cron Worker** → Container Apps Job (scheduled)
- **Frontend** → Static Web Apps (managed, free tier, native GitHub integration)

**Consequences**: Scales to zero where possible (PDF renderer, future jobs). Unified container tooling. Playwright works cleanly in CA Jobs.
**Revisit**: If cold-start latency on the PDF renderer becomes annoying, keep one replica warm. If we move to k8s, CA images transfer directly.

---

## ADR-007 — Data stores: Postgres Flexible Server + Blob Storage + Key Vault

**Context**: Relational data (users, analyses, comments, debates) + large objects (PDFs, avatars, raw agent JSON) + secrets.
**Decision**:
- **Postgres 16 Flexible Server** (Burstable B1ms) — all relational data; `pg_trgm` for username search (later)
- **Blob Storage** (Standard LRS, hot tier) — PDFs, avatars, raw JSON dumps, per-analysis summary.md, site assets
- **Key Vault** — all secrets; Managed Identity access from Container Apps

**Consequences**: No Redis needed — Postgres is plenty at our scale. LISTEN/NOTIFY handles fan-out to SSE. Blob signed URLs for time-limited download links.
**Revisit**: Redis if per-request cache hit rate warrants it; Cosmos DB if we ever need multi-region writes.

---

## ADR-008 — Inter-service queue: Azure Service Bus

**Context**: User explicitly preferred durability over simplicity. In-memory queues lose jobs on restart.
**Decision**: **Service Bus Standard** namespace. Queue `analyses.submitted` triggers the worker. Topics reserved for future fan-out.
**Consequences**: ~₹500/mo, but reliable job delivery, dead-lettering on repeated failures, durable across pod restarts. User-driven choice, documented as intentional over-engineering for peace-of-mind.
**Revisit**: Never — user's explicit preference.

---

## ADR-009 — Report editability: section-level regeneration + user-accept + versioning

**Context**: "Debate can modify report efficiently — only affected section regenerates. Keep versions."
**Decision**:
- Reports stored as **structured sections** (not one blob)
- Debate produces **proposed patches** attached to a debate turn
- Patches include a `target_section_id` and `new_content`
- Owner-only Accept action: regenerates the target section + its dependents, creates a new Version
- All previous Versions retained; user can browse via History sidebar

**Consequences**: Database model becomes section-oriented (see `02-architecture.md` §5). Section→agent mapping maintained in code. Accept flow needs LLM calls (not free) — soft-cap at 5 accepted patches per debate per day as abuse guardrail.
**Revisit**: If users frequently revert patches, add a "Revert to version N" path (trivial — it's data).

---

## ADR-010 — Social model: global feed, no follow graph, single 🔥 reaction

**Context**: User simplified from previous plan. Everyone implicitly friends. Simpler UI, fewer entities.
**Decision**:
- No `follows` table; feed = all public posts chronologically
- Threaded comments (one level depth)
- Single reaction (🔥), toggle-only, not counter
**Consequences**: Smaller surface area. If community grows beyond 30 people, follow system can be added additively (feed filter becomes "followed only" vs "global").
**Revisit**: When user count > 30 OR organic desire to mute/unfollow appears.

---

## ADR-011 — Moderation: DEFERRED, risk accepted

**Context**: User declined content moderation in Phase 2.
**Decision**: No AI safety filtering, no reporting button, no moderator role. Login-only browsing partially mitigates.
**Consequences**:
- **Risk**: an abusive comment or idea from a stranger signup goes uncaught
- **Mitigation**: closed group (friends); login gate; Hemanth can manually delete any content as the operator via direct DB (emergency) or an admin shortcut (nice-to-have)
- **Trigger for revisit** (must implement moderation before these):
  - User count >20
  - Someone outside Hemanth's known network signs up
  - A public-facing marketing page exists
  - Any user reports an issue
**Revisit trigger**: see above — whichever hits first.

---

## ADR-012 — Notifications: in-app only with 30-day auto-expire on read

**Context**: User wants in-app notifications with a clear button and auto-cleanup.
**Decision**: `notifications` table (user_id, kind, payload, read_at). Cron job runs daily: `DELETE WHERE read_at IS NOT NULL AND read_at < NOW() - INTERVAL '30 days'`. Unread retained indefinitely.
**Consequences**: No email infrastructure to maintain in Phase 2. Users who don't visit don't lose info. Cron stays tiny.
**Revisit**: When users ask for email/push — probably Phase 3.

---

## ADR-013 — PDF generation: server-side Playwright

**Context**: Need consistent PDF quality including SVG charts across all client browsers.
**Decision**: Dedicated Container App Job running Playwright + headless Chromium. API triggers render; PDF cached in Blob keyed by `(analysis_id, version_id)`.
**Consequences**: Container image is large (~400MB for Chromium). Cold start ~3s. Acceptable — PDFs are user-triggered and async-perceived. First download for a version = fresh render; subsequent = cache hit.
**Revisit**: If PDF generation becomes a hot path (>50/day), evaluate keeping renderer warm.

---

## ADR-014 — Regions: data in Central India, LLM cross-region

**Context**: User data residency + DPDP + Indian user base. Model availability dictates LLM region.
**Decision**:
- **Central India**: Postgres, Blob, Key Vault, Service Bus, App Insights, Container Apps
- **Azure AI Foundry**: wherever `gpt-5.3-chat` is available (stays on existing resource)
- **Static Web Apps**: global CDN, no region choice

**Consequences**: LLM calls cross-region (~60ms overhead). Egress costs minimal at our scale. DPDP-compliant data locality.
**Revisit**: If Azure ships `gpt-5.3-chat` in Central India, move the Foundry resource.

---

## ADR-015 — Infrastructure as Code: Bicep

**Context**: Azure-native (first-class tooling, no HCL language tax), Terraform alternative evaluated.
**Decision**: **Bicep** for all Azure resources. Modules for each service, parameterised per environment.
**Consequences**: Stay Azure-native; tooling ships with Azure CLI. If we ever multi-cloud, migrate — but we won't.
**Revisit**: Never, unless we multi-cloud.

---

## ADR-016 — CI/CD: GitHub Actions

**Context**: Repo is on GitHub (open-source). Native integration options.
**Decision**:
- **Backend**: GitHub Actions build → push to ACR → deploy to Container App (via Azure CLI)
- **Frontend**: GitHub Actions via SWA's built-in deployment action (`Azure/static-web-apps-deploy@v1`)
- **dev branch → dev env** (on merge to main)
- **tag `v*.*.*` → prod env** (manual promotion)
- **PR previews**: SWA gives this for free; backend previews deferred (manual spin-up if needed)

**Consequences**: Workflow files live in `.github/workflows/`. OIDC federation for Azure auth (no long-lived credentials in GitHub Secrets).
**Revisit**: If complexity outgrows YAML, migrate to Azure DevOps Pipelines. Unlikely.

---

## ADR-017 — Monorepo

**Context**: User chose monorepo.
**Decision**: Single repo `chapter-one/` with `backend/`, `frontend/`, `infra/`, `docs/`, `.github/`.
**Consequences**: Simpler coordination of FE+BE API changes. CODEOWNERS file governs review scope as the team grows. Semantic-release only if we start shipping SDKs.
**Revisit**: If repo grows >10K files, consider split.

---

## ADR-018 — Environments: prod + dev (no staging)

**Context**: 5 users, solo maintainer. Staging is overhead we can't afford to maintain.
**Decision**: Two environments — dev (loose, auto-deploy) and prod (tagged, manual promotion). Dev URL not publicly linked.
**Consequences**: Less regression safety than with a staging tier. Compensate with solid automated tests + canary-style manual testing of a new tag before promoting.
**Revisit**: When contributor count exceeds 3 or prod outages cost user goodwill.

---

## ADR-019 — Open-source licence: MIT

**Context**: Open to contributors. Permissive licence aligns with "use it however you want" ethos.
**Decision**: **MIT** (confirmed by user in Round 4).
**Consequences**: Anyone can fork + run a SaaS of Chapter One. If that ever becomes a concern, consider switching to AGPL for future commits (existing MIT code stays MIT). `LICENSE` file lives at repo root, copyright "Chapter One contributors".
**Revisit**: If commercial concerns appear, consider dual-licensing future commits as AGPL + commercial.

---

## ADR-020 — Progress streaming: Postgres LISTEN/NOTIFY + SSE (not SignalR)

**Context**: Worker runs in separate Container App from API; need real-time push to browser.
**Decision**: Worker writes to `analysis_events` table + fires `NOTIFY analysis:{id}`. API's SSE handler does `LISTEN` on the channel and streams events to the client.
**Consequences**: No extra Azure service. Single source of truth in Postgres. Reconnects replay history cleanly (`SELECT … WHERE analysis_id = … ORDER BY ts`).
**Revisit**: If concurrent SSE clients exceed ~50, move to Azure SignalR.

---

## ADR-021 — Charts: server-rendered SVG (inherited from Phase 1)

**Context**: Phase 1 eliminated Mermaid after repeated failures and switched to matplotlib-rendered inline SVG.
**Decision**: Unchanged.
**Consequences**: Reports are self-contained markdown+SVG. PDFs trivially preserve charts (Playwright renders SVG natively).
**Revisit**: Only if we need interactive charts (hover tooltips, drill-down) — then switch to Recharts in the frontend. Not for Phase 2.

---

## ADR-022 — Username: immutable after set

**Context**: URLs embed username (`/{username}/reports/{slug}`). Mutable usernames break links.
**Decision**: Once set, username cannot be changed. Display name is mutable.
**Consequences**: Users must be deliberate at signup. Acceptable friction.
**Revisit**: If frustration emerges; implementable later with automatic redirects for old usernames (Instagram model).

---

## ADR-023 — Slug generation: auto from title, disambiguate with suffix

**Context**: Slugs need to be URL-safe + descriptive + stable.
**Decision**: On publish, compute slug = lowercase + hyphenated + strip punctuation of idea title (first 8 words); if collision with same user, append `-2`, `-3`. **Immutable after publish.**
**Consequences**: SEO-friendly URLs. Users who want a prettier slug can tweak before publish (optional UI).
**Revisit**: Not expected.

---

## ADR-024 — Debate transcript: shared, not per-user

**Context**: Multiple users can debate the same report. Question: one thread for everyone, or one per user?
**Decision**: **Single shared thread per report**. All users see each other's turns.
**Consequences**: Community-like dynamic; users can build on each other's arguments. Potential downside: heated debates visible to all — risk accepted for friends-only launch.
**Revisit**: When moderation goes public (ADR-011 trigger).

---

## ADR-025 — Rate-limit middleware design: build scaffolding, enforce later

**Context**: 5 users = no need for rate limits. But retrofitting is painful.
**Decision**: Ship auth middleware with a `@rate_limit(limit, window)` decorator stub that's a no-op in Phase 2. Flip switch when we open up.
**Consequences**: Tiny upfront cost, large future leverage.
**Revisit**: When user count > 20 or when a single user consumes >₹500/day.

---

## ADR-026 — Debate grounding sources: retrieval + live search + report

**Context**: "No hallucination" requirement.
**Decision**: Every debate turn gets:
1. Retrieval over stored `agent_outputs` (keyword relevance, no embeddings in Phase 2)
2. Live `web_search` call if user-introduced entities not in stored research
3. Current report's affected sections
4. Last N turns of debate history
System prompt enforces citations + "I don't know" on ungrounded claims.
**Consequences**: Each turn = 1-2 LLM calls (~₹3 each). 20-turn debate ≈ ₹60. Within budget.
**Revisit**: Add embeddings-based retrieval when stored research exceeds ~100K tokens (Phase 3).

---

## Pending verifications (not blocking design)

- **ADR-014** — Central India vs South India region final pick — verify SKU availability when the Azure subscription is wired up
