# Chapter One — Security Model

> Scope: authentication, authorization, data protection, secrets, uploads, CORS/CSP, and a STRIDE threat model with mitigations.
>
> Deliberately out of scope in Phase 2: content moderation (ADR-011), intrusion detection, WAF (can add Front Door later).

---

## 1. Authentication

### 1.1 OIDC flow — sign-in

```
[Browser]                     [Frontend (SWA)]            [Entra External ID]        [Google]            [Backend API]
    │                                │                           │                     │                      │
    ├── click "Continue with Google" │                           │                     │                      │
    │───────────────────────────────▶│                           │                     │                      │
    │                                ├── redirect /authorize ────▶                     │                      │
    │                                │                           ├── federate ────────▶│                      │
    │                                │                           │ ◀─── id_token ──────┤                      │
    │                                │ ◀── redirect with code ───┤                     │                      │
    │ ◀──────── 302 /api/v1/auth/callback/google?code=... ───────┤                     │                      │
    │                                │                           │                     │                      │
    ├── GET callback?code=... ───────────────────────────────────────────────────────────────────────────────▶│
    │                                │                           │                     │                      ├── exchange code
    │                                │                           │                     │                      │   → Entra tokens
    │                                │                           │                     │                      ├── verify id_token signature
    │                                │                           │                     │                      │   (JWKs cached)
    │                                │                           │                     │                      ├── upsert user row
    │                                │                           │                     │                      ├── Set-Cookie: co_session
    │ ◀──────────────────────── 302 / (or /onboarding) ──────────────────────────────────────────────────────┤
    │                                │                           │                     │                      │
```

### 1.2 Session cookie

| Attribute | Value | Why |
|---|---|---|
| Name | `co_session` | — |
| Value | Encrypted blob: `{user_id, external_id, issued_at, expires_at}` via Fernet (key in Key Vault) | Opaque to client |
| HttpOnly | `true` | No JS access → XSS-resistant |
| Secure | `true` | HTTPS-only |
| SameSite | `Lax` | Allows OAuth redirect, blocks cross-site POSTs |
| Path | `/` | App-wide |
| Max-Age | 30 days | Rolling refresh on every request |
| Domain | `.chapterone.app` (once custom domain) or SWA default | — |

### 1.3 Token refresh

Session is valid for 30 days rolling. Before expiry, the API silently refreshes the Entra token in the background using the refresh_token stored server-side in the session record. User never sees a re-login prompt inside the 30-day window unless they're inactive.

Inactive cookies expire and user is routed to `/login?next=...`.

### 1.4 Logout

`POST /api/v1/auth/logout`:
1. Clear `co_session` cookie (Set-Cookie with Max-Age=0)
2. Invalidate server-side session record (soft-expire `expires_at=NOW()`)
3. Optionally invoke Entra's end-session endpoint (best-effort)

---

## 2. Authorization

### 2.1 Subject types

- **Owner** — `users.id == analyses.owner_id`
- **Viewer** — any authenticated user for a public analysis
- **Commenter** — any authenticated user for a public analysis (can comment on others' public posts)
- **Anonymous** — accesses public share URLs only

### 2.2 Permission matrix

| Action | Owner | Viewer (auth) | Anonymous |
|---|---|---|---|
| View own private report | ✓ | — | — |
| View public report | ✓ | ✓ | ✓ |
| Submit analysis | ✓ (own) | ✓ (own) | ✗ |
| Delete analysis | ✓ (own) | ✗ | ✗ |
| Change analysis visibility | ✓ (own) | ✗ | ✗ |
| Post comment | own/public | public | ✗ |
| Delete own comment | ✓ | ✓ | — |
| Delete other's comment on my post | ✓ | ✗ | — |
| Drop 🔥 | own/public | public | ✗ |
| Debate (post turn) | ✓ | ✓ (public only) | ✗ |
| Accept patch | ✓ (owner only) | ✗ | ✗ |
| View debate | same as report visibility | same | 🔓 if public |

### 2.3 Enforcement

- All checks in FastAPI **dependency injectors** applied per-route (never in business logic)
- Never trust client-provided `owner_id` — always read from authenticated session
- DB row-level never exposed through an API (no ORM dump into response); use explicit serializers

---

## 3. Secrets management

All secrets live in **Azure Key Vault**. No secret appears in:
- Source code
- Environment variables set outside Key Vault references
- CI/CD logs
- Container images
- `.env` files committed to the repo (except `.env.example` with placeholders)

### 3.1 Managed identity access pattern

Container Apps → assigned System-Assigned Managed Identity → granted `Key Vault Secrets User` role → reads secrets at process startup (cached in-process for the pod lifetime).

### 3.2 Secrets inventory

| Secret | Owner system | Rotation |
|---|---|---|
| `azure-openai-api-key` | Azure AI Foundry | 90 days |
| `postgres-app-password` | App user for Flexible Server | 90 days |
| `google-oauth-client-secret` | Google Cloud (federated via Entra External ID) | 180 days |
| `session-encryption-key` | Fernet symmetric for session cookies | 180 days, rolling with overlap window |
| `service-bus-connection-string` | Azure Service Bus | 90 days |
| `blob-storage-sas-signing-key` | Storage account key (for SAS generation) | 90 days |
| `playwright-worker-shared-secret` | PDF worker webhook auth | 90 days |

---

## 4. User-uploaded content pipeline (avatars)

```
[Browser]              [Frontend]           [Backend API]           [Blob Storage]
   │                       │                     │                         │
   ├── pick file ──────────▶                     │                         │
   │                       ├── pre-validate size + type (client-side UX only) │
   │                       ├── POST /users/onboard (multipart) ────────────▶                         │
   │                                             ├── validate MIME from magic bytes (`python-magic`) │
   │                                             ├── reject if not jpeg/png/webp                     │
   │                                             ├── reject if >2MB                                  │
   │                                             ├── load image via Pillow, re-encode to webp @ 512×512 │
   │                                             ├── upload to avatars container ───────────────────▶│
   │                                             ├── store Blob URL in users.avatar_url              │
   │                                             │                                                   │
   │ ◀──────────────────── 201 Created ──────────┤                                                   │
```

Key properties:
- Client-side size/type check is UX only — server always validates
- Server **re-encodes** the uploaded image (Pillow → webp) — strips EXIF, renders SVG/SVG-in-PNG exploits inert
- Avatars container is **public read** (by design, matches profile-pic common pattern); no PII in filenames
- Filename: `{user_id}/{hash}.webp` — `hash` is SHA-256 of file bytes → dedup + cache-friendly
- Previous avatar deleted from Blob on replace

---

## 5. CORS & CSP

### CORS

- Backend allows only `https://{env}.chapterone.app` (and `http://localhost:3000` in dev)
- Credentials: `true` (for cookie auth)
- Methods: `GET, POST, PATCH, DELETE, OPTIONS`
- Headers allowed: `Content-Type, Authorization, Idempotency-Key, Last-Event-ID`
- Max-Age on preflight: 3600

### CSP (set by the frontend; strict)

```
default-src 'self';
script-src 'self' 'unsafe-inline' https://accounts.google.com;  -- unsafe-inline needed for Next.js hydration; upgrade to nonce-based in Phase 3
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob: https://*.blob.core.windows.net;
font-src 'self';
connect-src 'self' https://*.azurestaticapps.net https://*.containerapps.io wss://*.containerapps.io https://login.microsoftonline.com;
frame-ancestors 'none';
base-uri 'self';
form-action 'self' https://login.microsoftonline.com;
```

Also send:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`

### 5.1 SVG in markdown — the inline-SVG concern

Our reports contain inline SVG from the chart generator. SVG can carry `<script>` tags. Our mitigation:
- Frontend renders markdown via `react-markdown` + `rehype-raw` (raw HTML allowed) + **`rehype-sanitize` with an SVG-friendly allowlist** that strips `<script>`, `on*` attributes, `<foreignObject>`
- Backend-generated SVGs are known-safe (matplotlib doesn't emit scripts), but LLM-generated content going through debate CANNOT be trusted — sanitizer is non-negotiable

---

## 6. STRIDE threat model

### S — Spoofing identity

| Threat | Mitigation |
|---|---|
| Attacker forges session cookie | Fernet-encrypted with Key Vault-held key; cookie is opaque; server validates integrity |
| Attacker impersonates another user via stolen Entra token | HttpOnly cookie mitigates JS theft; Secure attribute prevents clear-channel leak; short session + refresh flow |
| OIDC callback CSRF | `state` parameter in OIDC flow (signed, single-use) |
| Username squatting via race | DB unique constraint + serializable transaction on `POST /users/onboard` |

### T — Tampering

| Threat | Mitigation |
|---|---|
| SQL injection | Parameterised queries only (asyncpg/SQLAlchemy); no string-concat SQL |
| Modifying report content via API | Only owner can POST edits; accepted patches go through section-regen, not user-uploaded content |
| MITM alters response | HTTPS + HSTS everywhere |
| Client-supplied analysis_id references another user's report | Every access checks visibility + ownership in dependency injector |

### R — Repudiation

| Threat | Mitigation |
|---|---|
| User denies deleting their account | `deletion_audit` table (hashed user_id, counts, timestamp) kept 30 days |
| User denies posting a comment | App Insights trace with correlation ID + session ID tied to every mutation |
| User denies accepting a patch | `debate_patches.decided_by + decided_at` fields |

### I — Information disclosure

| Threat | Mitigation |
|---|---|
| Private report leaks via predictable URL | UUIDs + slug (not sequential IDs); owner-check on every read |
| `/users/{username}` enumeration reveals who's registered | Acceptable — usernames are public by design |
| `/public/reports/{u}/{slug}` distinguishes "doesn't exist" from "private" | Both return 404 — deliberate ambiguity |
| Idea text leaks via telemetry | `LOG_IDEA_TEXT=false` default; App Insights redaction for known fields |
| Blob URLs in public containers leak avatars of deleted users | Deletion pipeline removes blob objects synchronously |
| LLM prompt injection extracts other users' data | Sanitize debate input; isolate per-analysis context; never include other users' data in prompts |

### D — Denial of service

| Threat | Mitigation |
|---|---|
| One user submits thousands of analyses draining LLM quota | Phase 2: small group + Azure Foundry quota caps. Phase 3: per-user limits flipping on via the stub rate-limit middleware (ADR-025) |
| Comment spam | Rate limit on `POST /comments` (50/hr per user — Phase 3) |
| Blob storage fills up with big uploads | 2MB avatar cap, server-enforced |
| Budget breach | Azure Cost alert at 75%, 90% of monthly cap; past cap Azure pauses services |
| SSE connection exhaustion on API pod | Per-pod connection cap (~1000) + reconnect from client; Container Apps auto-scales on concurrency |

### E — Elevation of privilege

| Threat | Mitigation |
|---|---|
| User edits another user's analysis | Owner check at every mutation endpoint; 403 otherwise |
| User accepts a patch on someone else's report | Accept endpoint checks `analyses.owner_id == session.user_id` |
| Compromise of API pod reads secrets | Managed Identity + scoped Key Vault role; compromised pod has its own identity and limited blast radius |
| Contributor PR adds a privileged endpoint without review | `CODEOWNERS` requires Hemanth review on all `/auth`, `/users/*/delete`, `/debate/*/accept` paths |

---

## 7. Dependency security

- **GitHub Dependabot**: enabled on repo; weekly scans Python + npm
- **`pip-audit`** on CI — fails build on critical CVE
- **`npm audit --audit-level=high`** on CI
- **Container scanning**: ACR built-in Defender for Containers (Azure Defender plan — free tier covers small accounts)

---

## 8. Logging & observability privacy

- Idea text: **never logged** by default (`LOG_IDEA_TEXT=false`)
- User emails: logged at signup ONLY; never in subsequent telemetry
- PII fields (email, username when used as identifier in debug): App Insights Telemetry Processor scrubs via custom processor
- Request bodies: not logged for mutations (only method, path, status, timing)
- Errors include stack traces but **not** variables containing user data

---

## 9. Data encryption

- **In transit**: TLS 1.2+ everywhere (managed certs on Container Apps ingress + SWA + Postgres Flexible Server + Blob)
- **At rest**:
  - Postgres: Microsoft-managed encryption (default)
  - Blob: Microsoft-managed encryption (default)
  - Key Vault: HSM-backed
- **In process**: session cookies Fernet-encrypted; PII in memory unprotected (standard)

Customer-managed keys (CMK) deferred to Phase 3 if/when a user requests higher compliance.

---

## 10. Incident response (basic)

No 24×7 ops — this is a hobby project. But if compromised:

1. **Revoke**: force-expire all sessions (`UPDATE sessions SET expires_at = NOW()`)
2. **Rotate**: roll every key in Key Vault via script
3. **Audit**: pull App Insights traces for the suspect time window
4. **Notify**: email affected users from Hemanth personally (no user-facing incident tooling in Phase 2)

Runbook for this in `07-operations.md` (Round 5).

---

## 11. Compliance posture

- **DPDP (India)**: user data in Indian Azure region, user can delete, consent implicit at signup
- **GDPR (EU)**: not actively targeting EU users in Phase 2; if signups arrive, delete-on-request + data residency disclosure will suffice
- **COPPA / children**: Google sign-in + Google's age gate handles this upstream; we add a Terms-of-Use clause "13+"
- **SOC 2 / ISO 27001**: not pursued in Phase 2
- **Azure trust inheritance**: we inherit all of Azure's certifications for the underlying services; published in the Azure Trust Center
