# Chapter One — Phase 2 Roadmap

> Milestones M0-M6 with acceptance gates. Each milestone ends with a demoable state. Timeline estimates assume a solo builder working evenings + weekends; contributors reduce elapsed time.

---

## Timeline overview

```
Week  1   2   3   4   5   6   7   8   9   10  11  12  13  14
        ═══════════════════════════════════════════════════════
  M0 ▄▄▄▄▄                                                      infra bootstrap
  M1    ▄▄▄▄▄                                                   auth + onboarding
  M2        ▄▄▄▄▄▄                                              pipeline in cloud
  M3             ▄▄▄▄▄▄▄                                        feed + social
  M4                    ▄▄▄▄▄▄▄▄                                debate + patches
  M5                           ▄▄▄▄▄                            polish + PDF + shares
  M6                                ▄▄▄                         hardening + launch
```

Estimated **10-14 weeks to launch** for one solo builder. Parallelizable if contributors join.

---

## M0 — Infrastructure bootstrap (≈ Week 1-2)

**Goal**: dev + prod Azure environments exist, empty app running end-to-end on both, CI/CD live.

### Scope
- Create Azure subscription resource groups, VNet, Log Analytics, App Insights
- Bicep modules scaffolded (network, identity, KV, Postgres, Blob, ACR, Container Apps Env, Service Bus)
- Entra External ID tenants created (dev + prod) with Google federation configured
- Container Apps env + a placeholder "hello world" FastAPI app deployed to both envs
- Static Web Apps hosting a placeholder Next.js "Coming soon" page
- GitHub repo created, Dependabot + CODEOWNERS set up
- GitHub Actions workflows: `backend-ci`, `frontend-ci`, `infra-validate`, `deploy-dev`, `deploy-prod`
- OIDC federation between GitHub Actions and Azure working on both envs
- App Insights wired into placeholder backend, confirming events appear in the portal
- Budget alert configured at ₹12,500 cap

### Acceptance gates
- ✅ `curl https://<prod-api-fqdn>/health` returns 200
- ✅ Static Web App loads "Coming soon" on both envs
- ✅ Pushing to `main` auto-deploys to dev in <10 min
- ✅ Tag `v0.0.1` prompts manual approval, then deploys to prod
- ✅ App Insights shows `request` telemetry for the health endpoint
- ✅ `az deployment group what-if` on infra matches actual state

### Risks
- Entra External ID portal setup is manual and fiddly — budget half a day
- Container Apps VNet injection has strict subnet size requirements (/23 minimum for CAE)
- SKU availability in Central India — check `gpt-5.3-chat` isn't needed here (it's in Foundry, separate)

---

## M1 — Identity + user profile (≈ Week 3-4)

**Goal**: users can sign in with Google, complete onboarding, see a profile page.

### Scope
- **Frontend**
  - Landing page (logged out): Chapter One hero + "Continue with Google"
  - Onboarding flow (`/onboarding`): username + display name + avatar picker
  - Header nav with user menu (once logged in)
  - Settings page with delete-account action (skeleton, full wiring in M6)
- **Backend**
  - `POST /api/v1/auth/callback/google` — OIDC token exchange + session cookie
  - `GET /api/v1/auth/session`, `POST /api/v1/auth/logout`
  - `POST /api/v1/users/onboard`, `GET /api/v1/users/me`, `PATCH /api/v1/users/me`, `GET /api/v1/users/{username}`
  - Session middleware + Fernet cookie encryption
  - `users` table with all denormalized stat fields
- **Infra**
  - Key Vault wired with session-encryption-key, google-oauth-client-secret
  - Avatar upload → Blob `avatars` container with image-pipeline (Pillow re-encode)

### Acceptance gates
- ✅ Fresh Google account can sign in → land on `/onboarding`
- ✅ Can pick username + avatar → land on empty `/feed`
- ✅ `/<username>` renders profile with zero analyses
- ✅ Second device: session persists across browser restart
- ✅ Logout clears the session
- ✅ Taken username → 409 error surface

---

## M2 — Pipeline migrated to the cloud (≈ Week 5-6)

**Goal**: the Phase 1 analysis pipeline runs end-to-end as a cloud service, storing results in Postgres + Blob.

### Scope
- **Backend**
  - Refactor pipeline into section-producing architecture (each agent now emits structured section payloads, not just prose)
  - `analyses`, `report_sections`, `report_versions`, `analysis_events`, `agent_outputs` tables via first Alembic migration
  - Worker entrypoint: Service Bus consumer that runs the pipeline
  - Progress streaming: worker writes to `analysis_events` + `pg_notify`; API `SSE` endpoint listens on `LISTEN`
  - Chart-placeholder substitution preserved (inherited from Phase 1)
  - `POST /api/v1/analyses`, `GET /api/v1/analyses/{id}`, `GET .../stream`, `GET .../report`
  - Observability layer adapted: App Insights sink + Blob for raw JSON + summary.md
- **Frontend**
  - `/new` page: submit-idea form
  - Progress view (reuses Phase 1 `ProgressStream` component with `detail` support)
  - Report view with server-rendered SVG charts
- **Infra**
  - Container Apps Job (analysis-worker) wired to Service Bus queue
  - Postgres schema deployed via Alembic-in-a-Job pre-deploy step

### Acceptance gates
- ✅ Submit an idea → SSE stream shows stage + detail updates → report renders
- ✅ Progress persists across API pod restarts (new connection replays events)
- ✅ Report shows all 5 SVG charts, inline, no Mermaid anywhere
- ✅ `/me/history` shows the user's past analyses
- ✅ App Insights shows full pipeline telemetry (research.query_fired, citations, etc.)
- ✅ Running two analyses in parallel: both complete without interference

### Risks
- First real test of cross-region LLM calls from Central India → latency regression needs measuring
- Service Bus concurrency tuning — start with concurrency=4, watch App Insights

---

## M3 — Social surface: feed, posts, comments, 🔥 (≈ Week 7-8)

**Goal**: community tab works — users can browse global feed, comment, react.

### Scope
- **Backend**
  - `posts`, `comments`, `fires`, `notifications` tables
  - `/api/v1/feed`, `/api/v1/posts/{id}`, `/api/v1/posts/{id}/comments` (CRUD), `/api/v1/posts/{id}/fires` (toggle)
  - Trigger-based denormalization (fire_count, comment_count)
  - Notifications engine (in-app only): triggered on fire, comment, reply
  - `GET /api/v1/notifications`, `PATCH .../read`, `DELETE .../*`
  - `GET /api/v1/notifications/stream` SSE
  - Notification cleanup cron (daily job)
- **Frontend**
  - `/feed` page with infinite scroll
  - Post card component (idea title + score + caption + preview chart + 🔥 + comments + download)
  - Comment thread (flat-with-parent rendering)
  - Fire micro-interaction animation
  - Notifications tab + unread badge
  - Clear-all / clear-one actions
- **Streak** logic wired into analysis completion handler; profile page shows stats

### Acceptance gates
- ✅ Public analysis appears in the global feed within 5s of completion
- ✅ 🔥 / comment on a friend's post → they see a notification
- ✅ Clearing notifications works (individual + all)
- ✅ Streak increments on a new-day analysis; visible on profile
- ✅ Private analyses don't appear in feed
- ✅ Mobile layout: cards render cleanly, 🔥 button easy to tap

---

## M4 — Debate + section patches (≈ Week 9-10)

**Goal**: the novel surface — debate an agent on a report and see the report update.

### Scope
- **Backend**
  - `debate_turns`, `debate_patches` tables
  - Debate engine: grounded LLM call combining stored research + optional live web_search + current report section + thread history
  - Patch detection — agent output may include a `proposes_patch` structured field
  - Accept-patch flow: section regeneration orchestrator
  - Section → dependent section mapping (see `02-architecture.md` §6)
  - `POST /api/v1/analyses/{id}/debate`, `GET .../debate`, `GET .../debate/stream`
  - `POST /api/v1/debate/patches/{id}/accept|dismiss`
- **Frontend**
  - Debate panel (right sidebar on desktop, bottom sheet on mobile)
  - Turn rendering with citation footnotes
  - Patch proposal card with Accept/Dismiss buttons
  - Version history sidebar on report view
  - Viewing past versions

### Acceptance gates
- ✅ User debates → agent responds with citations from stored research or fresh search
- ✅ Agent sometimes proposes a patch when evidence warrants
- ✅ Accepting a patch creates a new version and regenerates only affected sections
- ✅ Report shows the new version; history sidebar lists v1, v2, v3
- ✅ Can view any past version
- ✅ Agent says "I don't have data on that" when asked about ungrounded claims
- ✅ Owner-only accept enforcement

### Risks
- **This is the riskiest milestone** — grounded debate + section patching is novel
- Budget extra time for prompt iteration; Phase 1's prompt-tuning loop will repeat
- Cost awareness: a debate with many turns + accepted patches can easily be ₹150 — check App Insights per-analysis cost

---

## M5 — PDF + public sharing + polish (≈ Week 11-12)

**Goal**: a report can leave the platform via PDF or shareable public link.

### Scope
- **Backend**
  - PDF renderer Container App Job (Playwright + headless Chromium)
  - `GET /api/v1/analyses/{id}/report.pdf` with Blob caching
  - Public endpoints: `GET /api/v1/public/reports/{username}/{slug}` and `.pdf` (no auth)
  - Slug auto-generation on first publish, immutable after
  - Visibility toggle: `PATCH /api/v1/analyses/{id} {visibility}`
- **Frontend**
  - Share button on report: copies URL + opens native share sheet on mobile
  - Download PDF button on post cards + report
  - Public share page (logged-out friendly) — hero + report + "Sign up to try Chapter One" CTA
  - Settings: default visibility
  - Privacy toggle per report

### Acceptance gates
- ✅ Download PDF → renders with all charts + footer watermark
- ✅ Share URL shared outside Chapter One → opens for logged-out visitors
- ✅ Private report's share URL gives 404 (or gated message) for non-owners
- ✅ Re-rendering the same version returns cached PDF <1s
- ✅ Mobile share sheet integrates (iOS + Android Chrome)

---

## M6 — Hardening + launch (≈ Week 13-14)

**Goal**: delete-account works, security review done, 5 friends signed up and using it.

### Scope
- **Data deletion**
  - `DELETE /api/v1/users/me` with 202 async, background delete worker
  - Cascades through all related tables + blob assets
  - `deletion_audit` row
- **Security pass**
  - Dependency audit (`pip-audit`, `npm audit`)
  - CSP + security headers verified in production (securityheaders.com scan)
  - All secrets audited — no hard-coded values
  - OWASP top 10 sanity pass
- **Nightly backup verification workflow** running
- **Docs**
  - `README.md` + `CONTRIBUTING.md` public
  - Basic user-facing help page
- **Onboard your 5 friends**
  - They sign up, each submits an idea, we iterate on rough edges
  - Document any bugs in GitHub issues with label `first-cohort`

### Acceptance gates
- ✅ 5 users signed up and completed ≥1 analysis each
- ✅ ≥1 debate happened and completed successfully
- ✅ ≥1 patch accepted
- ✅ Delete-account wipes all data within 60s; hashed audit row remains
- ✅ No critical/high CVEs open
- ✅ Monthly cost trend on track to stay under ₹12,500

---

## Dependencies and parallelization

```
M0 ──┬─▶ M1 ──┬─▶ M2 ──┬─▶ M3 ──┬─▶ M4 ──┬─▶ M5 ──▶ M6
     │        │        │        │        │
     │        └────────┴────────┤        │
     │                          │        │
     └──── infra work parallel  │        │
                                │        │
                           frontend      backend
                           work can      patch engine
                           parallel      can parallel
                                         with PDF
```

Safe parallelizations (if contributors join):
- **M3's frontend** and **M4's backend** can overlap
- **M5's PDF** and **M4's patch engine** are independent
- **M6's deletion** wiring is small; can start during M5

Dangerous parallelizations (avoid):
- Changing section storage model (M2) while building debate patches (M4) — sequence them

---

## Risks & mitigation (roadmap-level)

| Risk | Mitigation |
|---|---|
| Debate grounding quality under-delivers | Budget extra prompt iteration in M4; fall back to "read-only debate" shipping if patches aren't reliable |
| Azure credits tight at cap | Scale down dev outside working hours (cron); reduce Log Analytics retention |
| Bicep deployments fail in obscure ways | Keep deployments small + incremental; `what-if` on every PR; teardown dev frequently to test bootstrap |
| Google OAuth quirks | Entra External ID is opinionated; validate flow early in M1 with a throwaway tenant |
| Central India SKU availability | If Postgres Flexible Server B1ms isn't available, fall back to Burstable B2ms (+₹1,500/mo) |
| Contributors introduce regression | CODEOWNERS + CI gates + small PRs; build a small suite of integration tests in M2 |
| User feedback reshapes the product | Timebox each milestone; explicitly defer scope creep to Phase 3 |

---

## What "done" looks like

At the end of M6, **Chapter One is**:

1. A live SaaS at an Azure-hosted URL
2. 5 friends using it as their idea-evaluation scratchpad
3. Every report sourced, downloadable as PDF, shareable publicly
4. Running within ₹12,500/month on VS Enterprise credit
5. Fully observable via App Insights
6. An open-source MIT repo anyone can read and contribute to

**Non-goals reminder (from `00-overview.md` §5):** idea generator, monetization, email/push, moderation UI, follow graph, team workspaces — all Phase 3+.

---

## Post-launch Phase 3 preview

Not part of Phase 2 but worth scoping now so M6 decisions don't foreclose them:

- Idea generator (original Prompt 12)
- Content moderation (Azure AI Content Safety pre-publish)
- Rate limits flipped on
- Email notifications (criticals only)
- Follow graph + "friends-only" feed filter
- Paid search provider (Serper.dev) behind abstraction we already designed
- Report-diff view (version N vs version M)
- User-facing analytics ("this week you made 3 analyses, averaged 68/100")
- Custom domain + branded landing page

All of this is net-additive — the Phase 2 architecture does not preclude any of it.

---

## Sign-off checklist (promotes docs from Draft v1 → v1.0 Approved)

Before building starts:

- [ ] Hemanth reviewed `00-overview.md` — personas, goals, non-goals correct
- [ ] Hemanth reviewed `01-requirements.md` — every FR matches product intent
- [ ] Hemanth reviewed `02-architecture.md` — stack choices approved
- [ ] Hemanth reviewed `03-data-model.md` — schema matches feature intent
- [ ] Hemanth reviewed `04-apis.md` — API contracts align with UX vision
- [ ] Hemanth reviewed `05-security.md` — risk posture acceptable (moderation deferred acknowledged)
- [ ] Hemanth reviewed `06-infrastructure.md` — SKU choices + cost envelope OK
- [ ] Hemanth reviewed `07-operations.md` — CI/CD + App Insights approach approved
- [ ] Hemanth reviewed `08-cost-model.md` — ₹12,500 monthly ceiling math confirmed
- [ ] Hemanth reviewed this roadmap — timeline + milestone scopes OK

After sign-off, docs move from "Draft v1" to "v1.0" status and **M0 begins**.
