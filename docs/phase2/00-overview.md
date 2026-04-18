# Chapter One — Phase 2 Overview

> **Status**: Draft v1 · Architect-led discovery in progress
> **Product name**: Chapter One
> **Tagline**: *"It all starts with Chapter One."*
> **Repository**: (to be renamed) `chapter-one` — monorepo, open-source MIT

---

## 1. Product one-liner

**Chapter One** is a collaborative idea-evaluation platform where friends generate, analyse, debate, and share startup ideas using a grounded-research AI agent.

Every idea becomes a **report** built on the Composite VC Framework (CVF, 10 dimensions, web-search-grounded), shared in a global feed, and open to factual debate that can update the report section-by-section.

## 2. Why it exists

Hemanth and his ~5 friends want a place where they can:
- Brainstorm early ideas without gatekeepers
- Get a rigorous, research-backed read on each idea
- Push back on the AI's verdict with facts and see the report update
- Cheer each other on (streaks, fires, visible progress)
- Share finished reports outside the platform (public link, PDF)

Phase 1 proved the analysis quality is achievable on Azure AI Foundry (`gpt-5.3-chat` + web_search) at ~$0.10 per analysis. **Phase 2 turns that single-user local tool into a cloud-hosted social product for the friend group, architected to open up to the public later without a rewrite.**

## 3. Personas

### P1 — The Author (primary)
- Demographic: Hemanth + 5 friends, Indian tech professionals, 25-35, desktop-first
- Goal: get a high-quality, fact-backed analysis of an idea they're considering; show their friends
- Frequency: a few ideas per week in bursts, then quiet stretches
- Key expectation: **honesty over optimism** — the agent must flag weaknesses
- Success looks like: "The report called out the competitive moat weakness I'd been ignoring; my friend agreed in the comments."

### P2 — The Collaborator
- Same cohort as P1 but acting on *someone else's* idea
- Goal: read a friend's report, comment, throw a 🔥, maybe debate the agent if they think a score is off
- Frequency: daily/weekly engagement, mobile-first often
- Key expectation: **fun + social** — it should feel like checking up on a friend's post, not filing a form
- Success looks like: "I disagreed with the GTM score, debated the agent, and the report updated with my point as a new version."

### P3 — The Visitor (deferred but designed-for)
- An external viewer of a public share link — a potential investor, a teammate outside the circle, a curious stranger
- Goal: read a specific report someone sent them
- Frequency: one-time visits via direct link
- Key expectation: **credibility** — the report must look professional, sourced, shareable
- Success looks like: "I got this report link, it rendered well, the sources were real, I know this person did their homework."

## 4. Phase 2 goals (what "done" means)

Primary goals — **all must be true at launch**:

1. **Multi-user, sign in with Google** — Entra External ID, Google OAuth, first-come usernames
2. **Analysis pipeline runs in the cloud** — long jobs on Container Apps Jobs, state persisted across restarts, progress streamed via SSE
3. **Reports persist forever** (until user-initiated delete), with full version history
4. **PDF export** — server-rendered, charts intact, Chapter One footer watermark
5. **Global feed** — summary cards, captions, 🔥 reactions, threaded comments, download button
6. **Public share links** — `/{username}/reports/{slug}` readable by anyone, no login required
7. **Debate sidebar** — anyone can debate any visible report; agent responses are grounded (stored research + live search); accepted debate turns **patch affected sections** and create a new report version
8. **Streaks & profile stats** — current/longest streak, total ideas, 🔥 received, joined date
9. **Hard-delete** — one button on profile that wipes user + all their data (reports, debates, comments, fires, blobs, transcripts)
10. **In-app notifications tab** with clear/dismiss + 30-day auto-expiry on read items
11. **Fully responsive UI** — mobile, tablet, desktop
12. **All data in Azure, primary region Central India**

## 5. Non-goals (explicitly OUT of Phase 2)

The following are intentionally deferred. Putting them here so they don't scope-creep:

- Idea generator feature (the original Prompt 12)
- Monetization / billing / plans
- Email, SMS, push notifications — in-app only
- Content moderation — risk accepted for closed-group launch (see ADR-011, revisit trigger defined)
- Follow/friend graph — everyone auto-follows everyone in Phase 2
- Rate limits / abuse prevention — not needed at 5 users; revisit on public launch
- Real-time multi-user cursors on a report (not Figma)
- Mobile-native app (iOS/Android) — web is enough
- Team workspaces / organizations
- Admin / usage dashboard — use Azure Monitor for now
- Custom domain at launch (use `*.azurestaticapps.net`)
- Webhook / public API for third parties
- Export to Notion / Google Docs / Slack
- Compare two ideas side-by-side
- Multi-language UI (English only)
- Multi-reaction emojis (only 🔥)
- Report caption markdown, mentions, hashtags
- Search — feed is chronological only in Phase 2

## 6. Product pillars

Everything we build in Phase 2 serves one of four pillars. If a feature doesn't, it doesn't belong in Phase 2.

### Pillar A — Research quality is non-negotiable
Every claim has a source URL. Every search prefers <12-month-old data. The debate agent cannot fabricate facts. If data isn't available, the agent says so. This is what distinguishes Chapter One from any ChatGPT session.

### Pillar B — Debate without drift
The AI must stay neutral and evidence-bound when a user pushes back. It should neither cave to the user's framing nor stubbornly defend its own. The debate updates the report only when new evidence warrants it, tracked as a new version.

### Pillar C — Social warmth
Streaks, fires, profile stats, notifications — this is a tool for a friend group, not an enterprise intranet. The UI should feel like Instagram or Snapchat, not SharePoint.

### Pillar D — Azure-native, operationally boring
No bespoke infrastructure. No self-run k8s. Managed services throughout. The operational surface should be small enough that one solo engineer (Hemanth) can keep it running on evenings and weekends.

## 7. Success criteria for Phase 2 launch

| Metric | Target |
|---|---|
| 5 friends signed up and using it | Week 1 |
| ≥5 analyses produced per week across the group | Month 1 |
| At least one debate leads to an accepted report patch | Month 1 |
| Monthly Azure spend | **≤ ₹12,500 (VS Enterprise cap)** |
| Report generation end-to-end failure rate | <5% |
| Reports with zero citations | **0** (always grounded) |
| p95 analysis completion time | <7 min (quality prioritized over speed) |
| Mobile lighthouse score | ≥85 |
| Hard-delete completion time | <60s, fully purges Azure data |

## 8. Glossary (definitions used throughout)

| Term | Meaning |
|---|---|
| **Idea** | A natural-language pitch submitted by a user, ≥20 chars |
| **Analysis** | The machine-generated research + scorecard for an idea |
| **Report** | The rendered markdown + SVG charts of an Analysis |
| **Section** | A self-contained block of the Report (e.g. "Problem severity", "Market size") — unit of editability |
| **Version** | A snapshot of a Report at a point in time — created on accepted patches |
| **Debate** | A thread of turns between users and the agent attached to a Report |
| **Patch** | A proposed section change from a debate turn; creates a new Version on accept |
| **Post** | An Analysis made visible in the global feed (optional caption + summary card) |
| **🔥 (Fire)** | The single reaction type; count aggregated per Post and on user profile |
| **Streak** | Consecutive calendar days with ≥1 completed Analysis |
| **Share link** | Public URL `/{username}/reports/{slug}` viewable without login |

---

## Related documents

- [`01-requirements.md`](01-requirements.md) — detailed FRs / NFRs
- [`02-architecture.md`](02-architecture.md) — system design
- [`10-decisions.md`](10-decisions.md) — ADRs
- [`11-open-questions.md`](11-open-questions.md) — unresolved items
