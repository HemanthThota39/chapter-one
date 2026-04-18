# Chapter One — Phase 2 Requirements

> Every feature gets a stable ID (`FR-*` functional, `NFR-*` non-functional). Acceptance criteria use Given/When/Then where useful.

---

## Functional requirements

### FR-AUTH — Identity & profile

#### FR-AUTH-001 Google sign-in
- User can sign up and log in using **Continue with Google** via Entra External ID OIDC
- First sign-in creates a Chapter One account linked to the Google `sub` claim
- No email/password form at launch
- **Acceptance**: Given a fresh Google account, when the user clicks "Continue with Google" and consents, then they land on the onboarding page with no additional auth prompts

#### FR-AUTH-002 First-time profile onboarding
- After first login, user picks:
  - **Username** (3-20 chars, lowercase + digits + underscore, unique globally, first-come-first-served, **immutable after set**)
  - **Display name** (1-40 chars, free-form)
  - **Avatar** — three options:
    1. Upload image (≤2MB, jpg/png/webp, auto-resized to 512×512, stored in Blob)
    2. Pick from a library of 12 generated geometric avatars (pre-seeded, served from Blob)
    3. Initials (display_name first letter on a seeded background colour — no network cost)
- User cannot use the app until profile is complete
- **Acceptance**: New user without a complete profile → redirected to `/onboarding`; user with complete profile → any protected route renders

#### FR-AUTH-003 Logout
- Logout clears httpOnly cookies and revokes the session on backend
- **Acceptance**: After logout, hitting any protected route → redirects to login

#### FR-AUTH-004 Hard delete account
- Settings page has "Delete my account" destructive action (double-confirm)
- On confirm:
  - All Analyses, Reports, Versions, Debates, Comments, Fires, Posts, Notifications, Blob assets, transcript files owned by the user are **permanently deleted** (not soft-deleted)
  - User row removed
  - User's comments on others' reports: removed (no tombstones — we don't need a moderation trail)
  - **🔥 counts on other users' posts are decremented** as the user's fires are deleted
- Completes in <60s for a user with <500 assets
- Audit log of the deletion event kept for 30 days in a separate `deletion_audit` table (user_id hash + timestamp only, no PII) for our own ops sanity
- **Acceptance**: A deleted user's username becomes available for re-registration; their public share links 404; their comments vanish from others' threads

---

### FR-ANALYZE — Idea analyzer

#### FR-ANALYZE-001 Submit idea
- Authenticated user can submit an idea via `POST /api/analyses` with:
  - `idea_text` (20-4000 chars)
  - Optional `visibility` (`public` | `private` — default per user setting; see FR-AUTH-005)
- Server responds `202 Accepted` with `{analysis_id, status: "queued"}` within 500ms
- Analysis runs asynchronously — see runtime view in `02-architecture.md`
- **Acceptance**: Submitting `<20` chars returns 400; submitting while a prior analysis is running is allowed (no rate limit in Phase 2, see NFR-RATE)

#### FR-ANALYZE-002 Progress stream
- `GET /api/analyses/{id}/stream` returns an SSE stream emitting:
  - `progress` events (7 coarse stages — see existing pipeline)
  - `detail` events (per-query sub-steps, agent starts)
- Stream closes on terminal state (`done` | `error`)
- Reconnection: if the client reconnects mid-run, it receives:
  - The **full history of progress + detail events** so far (replay from DB)
  - Then live updates as they arrive
- **Acceptance**: Closing the tab mid-analysis and reopening the analysis detail page shows current stage without losing continuity

#### FR-ANALYZE-003 Report rendering
- On completion the report is stored as a structured object:
  - `sections: [{id, title, content_md, source_agents[], generated_at, version_id}]`
  - Rendered markdown is computed on demand by concatenating sections
- Charts are server-generated SVGs (as in Phase 1), stored inline in the section markdown
- **Acceptance**: `GET /api/analyses/{id}` returns metadata; `GET /api/analyses/{id}/report` returns the composed markdown; `GET /api/analyses/{id}/report.pdf` returns the PDF (FR-PDF-001)

#### FR-ANALYZE-004 Research quality preserved
- All Phase 1 research-quality rules carry over:
  - Per-query multi-search engine
  - Median-reconciliation across conflicting sources
  - Freshness bias toward last 12 months
  - Every finding has a source URL
- **Acceptance**: No report is shipped with zero citations; `data_quality_warning` populated when sources were thin; observability logs include all research events as in Phase 1

---

### FR-HIST — Report history

#### FR-HIST-001 User's history page
- `/me/history` (also reachable from profile menu) lists all analyses owned by the user
- Each row: title, verdict badge, overall score, visibility, created_at, "View" and "Delete" actions
- Paginated (20 per page); sortable by created_at; filterable by visibility
- **Acceptance**: New user sees empty state with "Submit your first idea" CTA; user with 50 analyses sees pagination; delete from this page immediately removes the row

#### FR-HIST-002 Single-analysis delete
- User can delete one of their analyses (not the whole account)
- Cascades: Report versions, Debates, Comments, Fires on this Post, notification events referencing it
- Public share URL stops resolving; feed entry disappears
- **Acceptance**: Deleted analysis's share URL returns 404; its comments vanish from commenters' notification lists

---

### FR-SHARE — Public sharing

#### FR-SHARE-001 Share URL format
- URL shape: `/{username}/reports/{slug}`
- `slug` is auto-generated on publish from the idea title (lowercase, hyphen-separated, suffix-disambiguated if collision: `-2`, `-3`, etc.)
- Slug becomes **immutable** once published
- **Acceptance**: Clicking a share URL while logged out renders the report (if visibility=public) or shows a "sign in to view" gate (if visibility=private)

#### FR-SHARE-002 Visibility toggle
- Per-report: `public` (anyone with URL can view, appears in feed) | `private` (only owner can view — does not appear in feed)
- Default at signup: `public`; user can change default in settings
- Toggle available on the report page and in history
- **Acceptance**: Toggling public→private removes the Post from all feeds within 5s; toggling private→public re-creates the Post

#### FR-SHARE-003 Copy link button
- "Share" button on the report page copies the fully-qualified URL (with https://…) to clipboard and shows confirmation toast
- Web Share API used on mobile browsers that support it (native share sheet)
- **Acceptance**: On iOS Safari, tapping Share opens iOS share sheet; on desktop Chrome, URL is copied to clipboard

---

### FR-PDF — PDF export

#### FR-PDF-001 Generate PDF
- Any report can be exported to PDF via `GET /api/analyses/{id}/report.pdf`
- Generated server-side using **Playwright** (headless Chromium) rendering the report page with a `?print=1` flag that applies a print-friendly stylesheet
- Pipeline:
  1. Request hits API → if PDF already cached in Blob for this version, stream it
  2. Else, launch Playwright, render the report HTML, `page.pdf()`, stash in Blob at `pdfs/{analysis_id}/{version_id}.pdf`, stream back
- Watermark / footer on every page:
  > `Generated by Chapter One · chapterone.app/{username}/reports/{slug} · {generated_at}`
- Includes all SVG charts intact
- **Acceptance**: Downloaded PDF opens in Preview/Acrobat with all charts, is ≤5MB for a typical report, footer present on every page

---

### FR-FEED — Community feed

#### FR-FEED-001 Global feed view
- `/feed` (also the default landing after login) shows all public Posts globally
- Reverse-chronological (newest first); infinite scroll; 20 items per page
- **Acceptance**: New public posts appear at top on refresh; private reports never appear; logged-out users cannot access `/feed`

#### FR-FEED-002 Post card contents
A card shows:
- Author avatar + display name + username + `·` + relative time
- Idea title
- Verdict badge (e.g. `CONDITIONAL 63/100`)
- One-line caption (optional, user-provided at publish time or editable later on own posts)
- One preview chart (CVF dashboard SVG — the one we already render in Phase 1)
- 🔥 count + button to drop a fire
- Comment count + button to open the comment thread
- Download icon (initiates PDF download)
- "View full report" CTA → `/{username}/reports/{slug}`

#### FR-FEED-003 Publishing and un-publishing
- When a user completes an analysis with visibility=public, a Post is auto-created and inserted into the feed
- User can edit the caption later (own posts only)
- User can set visibility=private → Post is removed from the feed

---

### FR-CMT — Comments

#### FR-CMT-001 Comment on a post
- Any logged-in user can comment on any visible Post
- Plaintext body, 1-1000 chars
- URLs in the text auto-linkify (frontend regex + backend sanitises before storage)
- No markdown, no mentions, no media
- **Acceptance**: Pasting `https://crunchbase.com/organization/x` renders as a clickable link; Markdown `**bold**` renders as literal text

#### FR-CMT-002 Threaded replies
- A comment can be a reply to another comment (one level of nesting only — "flat with parent", not deep threading)
- UI shows replies indented under the parent, max depth 1
- **Acceptance**: Reply to reply attaches at the same depth as reply-to-top-level

#### FR-CMT-003 Edit / delete own comment
- Author can edit their own comment (shows `(edited)` indicator after)
- Author can delete their own comment — body replaced with `[deleted]`, replies remain
- Post owner can delete comments on their own post (moderator role for own content)
- **Acceptance**: Deleted comment shows as `[deleted]`; replies remain visible with context

---

### FR-FIRE — 🔥 reactions

#### FR-FIRE-001 Fire on a post
- One fire per (user, post) — toggle on/off, not additive counter
- Aggregated: each Post has `fire_count`; each user has `fires_received` on profile
- Animated micro-interaction on tap/click
- **Acceptance**: Tapping 🔥 twice yields net zero; unique index on `(user_id, post_id)` in DB prevents double-fires

---

### FR-DEBATE — Debate on a report

#### FR-DEBATE-001 Open debate panel
- On any visible report, a "Debate" panel is available:
  - **Desktop**: right sidebar, toggleable
  - **Mobile**: bottom sheet / below the report
- Shows conversation history and an input field

#### FR-DEBATE-002 Conversation model
- Each Report has a **single shared debate thread** — all users' debate turns appear in it, chronologically, author shown per turn
- Each turn: `{user | agent, content_md, cited_urls[], proposes_patch?: SectionPatch, created_at}`
- **Acceptance**: User A debates, User B sees A's turns and can continue; conversation is persistent across sessions

#### FR-DEBATE-003 Grounded agent responses
- Every agent reply must:
  1. Ground itself in the saved research bundle first
  2. Run a **live web_search** when the topic requires post-training data OR when a user-introduced fact isn't in the stored research
  3. Cite every claim with a source URL (footnote-style or inline)
  4. Explicitly say "I don't have data on that" when no grounding is possible
- Unbiased: must consider both the user's position and the existing report's position, explicitly
- **Acceptance**: A sample of 10 debate turns shows ≥90% have citations; zero fabricated URLs (spot-check)

#### FR-DEBATE-004 Propose patch
- When an agent response meaningfully refutes or updates the report's content, the response includes a **SectionPatch**:
  - `target_section_id`
  - `change_summary` (1-2 sentences)
  - `new_section_content` (structured)
  - `rationale` (why this reflects reality better than the prior content)
- Rendered in the debate panel with:
  - Summary of what would change
  - **Accept** button (applies the patch → new report Version)
  - **Dismiss** button (patch recorded as rejected, report unchanged)
- Only the report owner can accept patches
- **Acceptance**: Accepting a patch creates a new Version; dismissing leaves it in the debate transcript but does not modify the report

#### FR-DEBATE-005 Section-level regeneration
- When a patch is accepted, only the **affected section(s)** and any **dependent sections** regenerate:
  - Direct section → re-run its source analysis agent with the debate context appended
  - Dependent sections → re-run if their inputs changed (e.g. dim score change → scorecard + overall score + recommendations)
- Section-to-agent mapping documented in `02-architecture.md`
- Report-level metadata (verdict, overall score) refreshes automatically
- **Acceptance**: Accepting a Competitive Moat patch regenerates the Moat section + scoring agent + recommendations agent, but not Market Size or Regulatory sections

---

### FR-VER — Report versioning

#### FR-VER-001 Versioned sections
- Every section has a version_id; the report has a current_version_id pointing to latest section versions
- New version created on accepted patch
- Previous section versions retained indefinitely in `report_section_versions` table

#### FR-VER-002 Version history UI
- Report page has a "History" icon opening a side panel listing all versions with:
  - Version number
  - Created_at + created_by (who accepted)
  - Change summary
  - "View this version" (renders the report at that point in time)
- **Acceptance**: Viewing v1 of a report that's now on v3 shows the v1 markdown

#### FR-VER-003 Version diff (stretch for Phase 2, required for Phase 3)
- Side-by-side or unified diff of what changed between two versions
- **Status**: Nice-to-have in Phase 2; required for Phase 3

---

### FR-STRK — Streaks & gamification

#### FR-STRK-001 Streak counter
- `current_streak` = consecutive calendar days (UTC or user timezone?) with ≥1 completed analysis
- `longest_streak` = max historical streak
- Timezone: **user timezone inferred from browser on first login, stored on user record**. All streak logic uses that zone to avoid "my 11pm IST analysis didn't count for today" bugs.
- **Acceptance**: Analysis completed at 23:59 IST counts for that IST day; analysis at 00:01 IST counts for the next

#### FR-STRK-002 Streak break visibility
- Broken streaks are **public** on the profile (no hiding)
- When a streak breaks, a notification is generated: "Your streak reset 🥺"

#### FR-STRK-003 Profile stats
- `/{username}` profile shows:
  - Avatar, display name, @username, joined date
  - Total analyses count
  - Current streak (with flame emoji, larger if ≥7 days)
  - Longest streak
  - Total 🔥 received across all their posts
  - Grid of their public reports (newest first, paginated)
- Private reports never appear on the public profile

---

### FR-NOTIF — Notifications

#### FR-NOTIF-001 In-app notifications
- Dedicated `/notifications` page + badge on header nav
- Events that generate notifications for the owner:
  - Someone 🔥'd your post
  - Someone commented on your post
  - Someone replied to your comment
  - Someone debated your report
  - A debate patch is pending your acceptance
  - Your streak is about to break (less than 4h remaining, fires only if user has visited today)
  - Your streak broke
  - Your analysis finished (if you navigated away from the progress page)
- Each notification: `{id, user_id, kind, payload, read, created_at, read_at}`
- **No email, no push, no SMS** in Phase 2
- **Acceptance**: Badge increments in real-time (via SSE or poll); clicking the notification navigates to the relevant entity

#### FR-NOTIF-002 Clear + auto-expire
- Each notification has a "Clear" (dismiss) button
- "Clear all" button on the page
- Auto-expiry rules:
  - Read: deleted 30 days after `read_at`
  - Unread: retained indefinitely until visited
- Daily cron job runs this cleanup
- **Acceptance**: A notification read 31 days ago is gone; a notification never read from 90 days ago is still there

---

### FR-DEL — Data deletion

Covered in FR-AUTH-004 (whole account) and FR-HIST-002 (single analysis). Key guarantees:

- Hard delete (no soft-delete, no tombstones except the ops-only deletion_audit row with no PII)
- Cascades across all entities related to the deleted subject
- Blob assets removed from storage (avatars, PDFs, raw agent JSON dumps)
- Search indexes (if any added later) invalidated

---

## Non-functional requirements

### NFR-PERF — Performance
- **NFR-PERF-001**: Analysis end-to-end p95 ≤ 7 min (quality > speed)
- **NFR-PERF-002**: Feed page initial load ≤ 1.5s on 4G mobile (Central India)
- **NFR-PERF-003**: Report page with charts load ≤ 2.5s
- **NFR-PERF-004**: SSE progress first event ≤ 3s after submit

### NFR-AVAIL — Availability
- **NFR-AVAIL-001**: Target 99% monthly uptime at launch (no SLA commitments to users)
- **NFR-AVAIL-002**: Backend deploys use **rolling update**, not blue/green (Container Apps default) — no pinning to a specific slot required
- **NFR-AVAIL-003**: Postgres Flexible Server with automated daily backups, 7-day PITR retention
- **NFR-AVAIL-004**: Blob Storage: LRS (locally redundant) is sufficient — not cross-region at this scale

### NFR-SEC — Security
- **NFR-SEC-001**: All secrets in Key Vault; Container Apps use Managed Identity
- **NFR-SEC-002**: All internet-facing endpoints TLS 1.2+ (managed certs via Container Apps ingress + SWA)
- **NFR-SEC-003**: Auth cookies: httpOnly, Secure, SameSite=Lax
- **NFR-SEC-004**: Rate limit on auth endpoints: 10/min per IP (basic abuse protection even though no overall rate limit)
- **NFR-SEC-005**: User-uploaded content (avatars): MIME-sniffed on server, extension whitelist, max size enforced
- **NFR-SEC-006**: SQL: parameterized queries only (asyncpg defaults are safe); no string-concat SQL
- **NFR-SEC-007**: Dependency scanning: GitHub Dependabot enabled on the repo

### NFR-A11Y — Accessibility
- **NFR-A11Y-001**: All interactive elements keyboard-reachable
- **NFR-A11Y-002**: Screen-reader labels on buttons
- **NFR-A11Y-003**: Colour choices in charts not solely dependent on hue (we already use distinct shapes + labels)
- **NFR-A11Y-004**: Target WCAG 2.1 AA for critical flows (submit analysis, read report, post/comment)

### NFR-OBS — Observability
- **NFR-OBS-001**: Structured logs via Application Insights (replaces Phase 1's file-based JSONL logs for cloud; local dev keeps files)
- **NFR-OBS-002**: All Phase 1 pipeline events preserved (query_fired, citations, synthesis, etc.) — now emitted to App Insights
- **NFR-OBS-003**: Per-analysis summary.md still generated, stored in Blob (`logs/{analysis_id}/summary.md`) for quick debugging
- **NFR-OBS-004**: Azure Monitor alerts on error_rate > 5% (5 min window), monthly cost trending over ₹10K

### NFR-COST — Cost
- **NFR-COST-001**: Monthly Azure spend ≤ ₹12,500 (VS Enterprise cap)
- **NFR-COST-002**: Monthly cost dashboard visible to Hemanth (Azure Cost Management)
- **NFR-COST-003**: Auto-alert at 75% of cap

### NFR-DATA — Data residency & retention
- **NFR-DATA-001**: All user data (PII, content) lives in an **Azure India region** (Central India preferred)
- **NFR-DATA-002**: LLM processing may be cross-region (East US 2 etc.) — Azure OpenAI does not persist prompt/response data
- **NFR-DATA-003**: Retention: forever until user-initiated deletion
- **NFR-DATA-004**: Backup retention: 7 days automated

### NFR-RATE — Rate limits (Phase 2 minimal)
- **NFR-RATE-001**: Not enforced in Phase 2 because of tiny user count, but design the auth-layer middleware to support it (so Phase 3 adds limits without refactor)
- **NFR-RATE-002**: Implicit LLM concurrency cap via Container Apps scale rule (prevents runaway cost)

---

## Assumptions

- Hemanth maintains the Azure subscription; billing issues don't block users
- Google is the sole IdP in Phase 2 — if Entra External ID's Google federation breaks, no fallback login
- The ₹12,500 credit cap is not exceeded in practice; if it is, Azure pauses services (acceptable for MVP)
- User timezones are IST majority; UTC-only storage, timezone-aware display

## Constraints

- `gpt-5.3-chat` availability dictates which region our AI Foundry resource lives in (currently `testingclaudecode.cognitiveservices.azure.com`, region TBD on verification)
- Azure AI Content Safety deliberately NOT adopted (see ADR-011)
- VS Enterprise subscription has SKU restrictions on some Azure services (notably premium storage tiers, some regions) — architecture picks SKUs within those limits

## Explicit risks

| Risk | Owner | Mitigation | Trigger for re-evaluation |
|---|---|---|---|
| No moderation → abusive content | Hemanth | Login-only; small closed group | When signups exceed 20 or a stranger is invited |
| Single region (Central India) → regional outage | Hemanth | Accept; restore from backups | When user count exceeds 500 |
| Service Bus is overkill → added complexity | Hemanth | Accepted for reliability per user preference | Never; user explicitly chose this |
| Debate costs scale nonlinearly | Hemanth | Track per-debate token cost; soft-cap at 20 turns per report per user per day | If any user exceeds ₹200/mo in debate tokens |
| Credit cap breached | Hemanth | Azure alert at 75%, 90% | Immediate |
