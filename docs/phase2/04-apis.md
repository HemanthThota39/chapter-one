# Chapter One — API Contracts

> Versioned at `/api/v1/*` (reserved prefix even though we don't maintain v0 → v1 today).
> All endpoints consume/produce `application/json` unless noted.
> Auth: cookie-based sessions (httpOnly, Secure, SameSite=Lax) issued after OIDC flow.
> Errors: RFC 7807 Problem Details.

---

## 1. Cross-cutting

### 1.1 Authentication

All `/api/v1/*` endpoints require an authenticated session **except** where marked **🔓 public**.

- Session cookie: `co_session` (httpOnly, Secure, SameSite=Lax, 30-day rolling)
- Server validates the Entra External ID JWT on every request and caches the parsed claims for the session lifetime
- `GET /api/v1/auth/session` returns the current user or 401

### 1.2 Error envelope (RFC 7807)

```json
{
  "type": "https://chapterone.app/errors/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "idea_text must be between 20 and 4000 characters",
  "errors": [{ "field": "idea_text", "code": "out_of_range" }]
}
```

### 1.3 Pagination

Cursor-based, not offset-based. Clients pass `?cursor={opaque}` and `?limit={1..50}`; responses include `next_cursor` (null if end).

```json
{ "items": [...], "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0wMy0xNVQxMDowMCJ9" }
```

### 1.4 Rate limiting (Phase 2)

Only applied on auth endpoints (10/min per IP). Other endpoints have no enforced limit. Every response includes `X-RateLimit-*` headers (stubbed) so clients can adapt once limits go live in Phase 3.

---

## 2. Auth + session

### `POST /api/v1/auth/callback/google` 🔓
Called by Entra External ID after Google consent. Exchanges code → tokens, issues session cookie.

### `GET /api/v1/auth/session`
Returns the current user's profile stub.
```json
{ "user": { "id": "uuid", "username": "hemanth", "display_name": "Hemanth", "avatar_url": "...", "onboarding_complete": true } }
```
401 if not authenticated.

### `POST /api/v1/auth/logout`
Clears the cookie. Returns 204.

---

## 3. Users

### `POST /api/v1/users/onboard`
First-time profile setup. Called once after signup.
```json
// request
{ "username": "hemanth", "display_name": "Hemanth T", "avatar_kind": "initials" }
// or for library pick:
{ "username": "...", "display_name": "...", "avatar_kind": "library", "avatar_library_id": "geo-07" }
// or for upload: multipart/form-data with 'avatar' file + other fields
// response 201
{ "user": { "id": "...", "username": "...", ... } }
```
Errors:
- 409 `username_taken`
- 400 `username_invalid` (bad chars)
- 413 `avatar_too_large` (if >2MB)
- 400 `avatar_unsupported_type`

### `GET /api/v1/users/me`
Full own profile including private settings.

### `PATCH /api/v1/users/me`
Mutable fields: `display_name`, `avatar_*`, `default_visibility`, `timezone`.
Username is **not** mutable (ADR-022).

### `GET /api/v1/users/{username}`
Public profile view.
```json
{
  "username": "hemanth",
  "display_name": "Hemanth",
  "avatar_url": "...",
  "joined_at": "2026-04-22T10:00:00Z",
  "stats": {
    "total_analyses": 14,
    "current_streak": 6,
    "longest_streak": 12,
    "fires_received": 37
  }
}
```
🔓 Accessible without login when the username exists.

### `GET /api/v1/users/{username}/posts?cursor=...&limit=20`
Public posts by this user. 🔓.

### `DELETE /api/v1/users/me`
Irreversible hard-delete. Two-step confirmation:
```json
// request (header)
X-Confirm-Username: hemanth
// body
{ "confirmation": "delete my account" }
// response
202 { "deletion_job_id": "uuid" }
```
Returns 202 immediately; deletion runs async (usually <60s). Subsequent `GET /session` returns 401.

---

## 4. Analyses

### `POST /api/v1/analyses`
Submit a new idea for analysis.
```json
// request
{ "idea_text": "An AI meeting notes ...", "visibility": "public" }
// response 202
{ "analysis_id": "uuid", "status": "queued" }
```

### `GET /api/v1/analyses/{id}`
Metadata + current version pointer. Access requires: owner OR report is public.
```json
{
  "id": "uuid",
  "owner": { "username": "...", "display_name": "...", "avatar_url": "..." },
  "idea_title": "...",
  "slug": "ai-meeting-notes-india",
  "visibility": "public",
  "status": "done",
  "overall_score_100": 63,
  "verdict": "CONDITIONAL",
  "confidence": "MEDIUM",
  "submitted_at": "...",
  "completed_at": "...",
  "current_version": { "id": "uuid", "version_number": 2 },
  "is_own": true,
  "can_debate": true
}
```

### `GET /api/v1/analyses/{id}/stream`
**Server-Sent Events** stream. Emits `progress` + `detail` events during analysis, plus a terminal event.

SSE event payloads:
```
event: progress
data: {"stage":"research","percent":15,"message":"Running parallel market research..."}

event: detail
data: {"message":"[market_sizing] searching: 'TAM AI meeting assistant 2026'"}

event: progress
data: {"stage":"done","percent":100,"message":"Analysis complete."}

event: close
data: {}
```

Replay semantics: on connect, the API first emits all prior events from `analysis_events` for that analysis, then live-streams new ones.

### `GET /api/v1/analyses/{id}/report`
Returns the composed markdown for the current version (or specified `?version=N`).

Accept types:
- `application/json` (default) → `{ "markdown": "...", "version_number": 2 }`
- `text/markdown` → raw markdown body, with `Content-Disposition: attachment` if `?download=1`

### `GET /api/v1/analyses/{id}/report.pdf`
PDF of the current version (or `?version=N`). Triggers render if not cached. Returns `application/pdf`.

### `GET /api/v1/analyses/{id}/versions`
List of all versions newest-first.
```json
{
  "items": [
    { "version_number": 3, "created_at": "...", "created_by_username": "friend2", "change_summary": "Accepted patch: updated Competitive Moat" },
    { "version_number": 2, "created_at": "...", "created_by_username": "hemanth", "change_summary": "Accepted patch: added MeetMinutes" },
    { "version_number": 1, "created_at": "...", "created_by_username": null, "change_summary": "Initial analysis" }
  ]
}
```

### `PATCH /api/v1/analyses/{id}`
Mutable fields for owner: `visibility`, `caption` (post caption), `slug` (pre-publish only).
```json
{ "visibility": "private" }
```

### `DELETE /api/v1/analyses/{id}`
Owner hard-deletes the analysis. Cascades per data model. Returns 204.

---

## 5. Feed

### `GET /api/v1/feed?cursor=...&limit=20`
Global chronological feed of public posts.
```json
{
  "items": [
    {
      "post_id": "uuid",
      "analysis_id": "uuid",
      "owner": { "username": "friend1", "display_name": "...", "avatar_url": "..." },
      "idea_title": "Low-code AI workflow builder",
      "caption": "Curious what you all think",
      "verdict": "CONDITIONAL",
      "overall_score_100": 63,
      "preview_chart_svg_url": "https://...blob.../cvf_dashboard.svg",
      "published_at": "2026-04-22T10:05:00Z",
      "fire_count": 4,
      "comment_count": 7,
      "i_fired": true,
      "share_url": "https://.../friend1/reports/low-code-ai-workflow-builder"
    }
  ],
  "next_cursor": "..."
}
```

### `GET /api/v1/posts/{post_id}`
Full post expansion (same shape as a feed item + the entire report markdown).

---

## 6. Comments

### `GET /api/v1/posts/{post_id}/comments?cursor=...&limit=50`
Flat-with-parent. Frontend reconstructs threading via `parent_id`.
```json
{
  "items": [
    { "id": "uuid", "author": {...}, "body": "Interesting take...",
      "parent_id": null, "is_edited": false, "is_deleted": false,
      "created_at": "...", "edited_at": null }
  ],
  "next_cursor": null
}
```

### `POST /api/v1/posts/{post_id}/comments`
```json
{ "body": "Nice idea — how do you plan to compete with X?", "parent_id": null }
// 201 response: full comment object
```

### `PATCH /api/v1/comments/{id}`
Only author. Sets `is_edited=true`, updates `edited_at`.

### `DELETE /api/v1/comments/{id}`
Author or post owner. Sets `is_deleted=true` (preserves threading), body replaced with `[deleted]` in responses.

---

## 7. Fires

### `POST /api/v1/posts/{post_id}/fires`
Toggles. Idempotent.
```json
// response
{ "fired": true, "fire_count": 5 }
```

---

## 8. Debate

### `GET /api/v1/analyses/{id}/debate`
All debate turns for the analysis, chronological.
```json
{
  "turns": [
    {
      "id": "uuid",
      "author_kind": "user",
      "author": { "username": "friend1", "display_name": "..." },
      "content_md": "I disagree — the competitive moat is weaker than you think because...",
      "cited_urls": [],
      "created_at": "..."
    },
    {
      "id": "uuid",
      "author_kind": "agent",
      "content_md": "You raise a valid point about switching costs. Per research cited below...",
      "cited_urls": ["https://..."],
      "proposes_patch": {
        "id": "patch-uuid",
        "target_section_key": "dim_5_moat",
        "change_summary": "Downgrade moat score from 7 to 5",
        "rationale": "Multiple sources show low switching cost...",
        "status": "pending"
      },
      "created_at": "..."
    }
  ]
}
```

### `POST /api/v1/analyses/{id}/debate`
Post a user turn; server synchronously runs the grounded agent response and returns the pair.
```json
// request
{ "content_md": "I think the market sizing is too conservative..." }
// response 201
{
  "user_turn": { "id": "...", ... },
  "agent_turn": { "id": "...", "cited_urls": [...], "proposes_patch": {...} },
  "agent_token_usage": { "input_tokens": 5423, "output_tokens": 812 }
}
```

### `GET /api/v1/analyses/{id}/debate/stream`
SSE stream for live updates when multiple users are debating the same report.
```
event: turn
data: {"turn_id":"...","author_kind":"user","preview":"I think..."}

event: turn
data: {"turn_id":"...","author_kind":"agent","has_patch":true}
```

### `POST /api/v1/debate/patches/{patch_id}/accept`
Owner-only. Triggers section regeneration, creates new report version.
```json
// response 202
{
  "patch_id": "...",
  "new_version": { "id": "...", "version_number": 3 },
  "regenerated_sections": ["dim_5_moat", "cvf_dashboard", "executive_summary", "recommendations"]
}
```

### `POST /api/v1/debate/patches/{patch_id}/dismiss`
Owner-only. Records dismissal on the patch; report unchanged.
```json
{ "patch_id": "...", "status": "dismissed" }
```

---

## 9. Notifications

### `GET /api/v1/notifications?cursor=...&limit=20&filter=unread|all`
```json
{
  "items": [
    { "id": "...", "kind": "fire", "payload": {...}, "read_at": null, "created_at": "..." }
  ],
  "next_cursor": "...",
  "unread_count": 7
}
```

### `GET /api/v1/notifications/stream`
SSE stream pushing new notifications in real time (used to update the header badge without polling).
```
event: new
data: {"id":"...","kind":"comment","payload":{...}}

event: unread_count
data: {"unread_count":8}
```

### `PATCH /api/v1/notifications/{id}/read`
Marks one as read.

### `POST /api/v1/notifications/read-all`
Bulk-marks all unread as read. Returns `{ "marked": 8 }`.

### `DELETE /api/v1/notifications/{id}`
Clears one.

### `DELETE /api/v1/notifications`
Clears all (read and unread). Returns `{ "cleared": 27 }`.

---

## 10. Public endpoints (no auth)

### `GET /api/v1/public/reports/{username}/{slug}` 🔓
Resolves a public share URL to its analysis. Returns full report markdown + minimal metadata.
```json
{
  "analysis_id": "...",
  "owner": { "username": "hemanth", "display_name": "Hemanth", "avatar_url": "..." },
  "idea_title": "...",
  "verdict": "CONDITIONAL",
  "overall_score_100": 63,
  "current_version_number": 2,
  "markdown": "...",
  "published_at": "..."
}
```

Returns 404 if the report is private or doesn't exist. No enumeration leakage — same error for "doesn't exist" vs "is private".

### `GET /api/v1/public/reports/{username}/{slug}/report.pdf` 🔓
PDF download of the current public version.

---

## 11. SSE event schemas (summary)

| Endpoint | Events | Payload shape |
|---|---|---|
| `GET /api/v1/analyses/{id}/stream` | `progress`, `detail`, `close` | `{ stage, percent, message }` / `{ message }` / `{}` |
| `GET /api/v1/analyses/{id}/debate/stream` | `turn`, `patch_proposed`, `patch_decided` | see §8 |
| `GET /api/v1/notifications/stream` | `new`, `unread_count` | see §9 |

SSE connections:
- Keepalive comment (`: ping\n\n`) every 25s to defeat proxy idle timeouts
- Clients MUST re-establish on disconnect; server replays missed events based on `Last-Event-ID` header (stored in the relevant events table)

---

## 12. Status code conventions

| Code | Meaning in Chapter One |
|---|---|
| 200 | OK — fetch success |
| 201 | Created — POST that created a resource |
| 202 | Accepted — async job enqueued (analyses, deletion) |
| 204 | No Content — PATCH/DELETE success |
| 400 | Validation error — look at `errors` array |
| 401 | Unauthenticated — missing/expired session |
| 403 | Forbidden — you don't own this resource |
| 404 | Not found OR not visible to you (deliberate ambiguity for private reports) |
| 409 | Conflict — username taken, slug collision |
| 413 | Payload too large — avatar upload |
| 422 | Unprocessable — idea text failed LLM classifier upstream |
| 429 | Rate limited — auth endpoints only in Phase 2 |
| 500 | Unexpected server error — always logged to App Insights |
| 503 | Service unavailable — Azure AI Foundry outage etc. |

## 13. Idempotency

`POST /api/v1/analyses` accepts an `Idempotency-Key` header. If the same key is posted twice within 24h with the same body, returns the original response. Stored in a small `idempotency_keys` table (not detailed above — keyed by `user_id + key`, 24h TTL).

## 14. OpenAPI spec

The actual OpenAPI 3.1 spec is auto-generated from FastAPI (`/openapi.json`) — this doc is the human-readable reference. Any discrepancy: the live OpenAPI wins and this doc is wrong; PR to fix.
