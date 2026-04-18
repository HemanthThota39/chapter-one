# Backlog — deferred features

Parked ideas that aren't blocking launch but should be picked up after
stabilization + public release. Ordered by product impact.

---

## 1. AI idea generation (multi-agent debate → one idea)

**Pitch.** Replaces the M4 "debate an existing report" concept with a
much more user-valuable flow: the user clicks *"Generate me a new
idea"*, and a committee of agents (research, market-sizing, founder
instinct, risk, GTM) argues, pulls real sources, and converges on one
concrete startup idea. Output is a full CVF report, same surface as a
user-submitted idea.

**Why it beats debate patches.**
- Debate-an-existing-report is a niche power-user feature; generating
  a *new* idea is value to everyone who opens the app with no idea.
- Reuses the existing scoring + report pipeline end-to-end — the new
  work is the ideation orchestrator + a converging arbitration round.
- Naturally viral: "this AI pitched me Uber for freight" is shareable.

**Sketch.**
- Orchestrator spawns N agents (roles above) with role-scoped system
  prompts. Round 1: each independently proposes one idea.
- Round 2: agents critique each other's pitches with research-grounded
  counters (real URLs, numbers).
- Arbiter merges + selects one winner (possibly synthesised) based on
  CVF-ish criteria.
- Hand off to the existing research → scoring → compiler pipeline.
- Store the debate transcript alongside the analysis (read-only) so
  users can see *why* the agents picked what they picked.

**Open questions.**
- Cost: each idea now burns 5-10× LLM calls vs. analysing a user idea.
  Rate-limit at 1-2/day per user.
- Does the arbiter need human-in-the-loop? (probably not for v1)
- Seed the generator with a domain/market/trend selected by the user,
  or fully open-ended?

---

## 2. Improvement suggestions on existing reports

**Pitch.** The CVF report already identifies weaknesses and assigns
per-dimension scores. Add a concrete *"How to make this stronger"*
section at the end that suggests product, market, or GTM pivots
targeting the lowest-scoring dimensions, with rationale.

**Why.**
- Turns the app from a graded-homework feeling into a coach.
- Much lighter than debate/patches; a single new compiler pass.
- Feeds back into engagement: users submit v2 of the same idea.

**Sketch.**
- New section `recommendations_pivot` added to the compiler.
- Input: current section outputs + dimension scores.
- Prompt: for each dimension scoring < 70, propose 2-3 targeted
  pivots with a 1-sentence why + expected score uplift.
- Render at the bottom of the report with an "Apply and re-analyse"
  button that pre-fills /new with the pivot text.

---

## 3. Public share link (PDF-only fallback)

**Status.** Skipped for launch — the card's Download PDF + OS share
sheet covers the 80% case. Users can still paste the PDF anywhere.

Revisit when: users ask for an HTML preview URL so recipients don't
need to download a file.

---

## 4. Rate limiting (N analyses / day per user)

**Status.** Skipped for launch. Add a DB-backed counter keyed on
`(user_id, UTC-date)`, soft limit 5/day, with a nicer "You've used
your quota" card.

Revisit when: cost per user > comfort threshold, or anti-abuse bites.

---

## 5. Debate + section-level patches (original M4)

**Status.** Dropped from the near-term roadmap. Replaced in practical
value by #1 (idea generation) and #2 (improvement suggestions).

Keep around as a spec reference in `docs/phase2/09-roadmap.md` §M4
and `04-apis.md` §8, but don't build unless a clear user need
surfaces post-launch.

---

## 6. Follow-mechanic + per-friend feed

**Status.** Not yet discussed. Current global feed is fine for the
initial 5-friends scope. Revisit when the user base grows past ~50.

---

## 7. Streaks

**Status.** Removed from UX on 2026-04-19. DB columns
(`current_streak`, `longest_streak`, `last_activity_date`) still exist
on `users` — harmless and cheap to re-enable if we reverse course.
