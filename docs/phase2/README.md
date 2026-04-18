# Chapter One — Phase 2 SRS

Living software-requirements-specification + architecture dossier for Phase 2 (cloud migration + multi-user social product) of Chapter One.

Status: **v1.0 APPROVED — signed off by Hemanth on 2026-04-18.** M0 implementation in progress.

## Reading order

1. [`00-overview.md`](00-overview.md) — product vision, personas, goals, non-goals, glossary
2. [`01-requirements.md`](01-requirements.md) — all functional + non-functional requirements with stable IDs
3. [`02-architecture.md`](02-architecture.md) — system context, container view, runtime flows, repo layout
4. [`03-data-model.md`](03-data-model.md) — Postgres schema, indexes, cascades, triggers, retention
5. [`04-apis.md`](04-apis.md) — HTTP contracts, SSE events, error envelope, idempotency
6. [`05-security.md`](05-security.md) — auth flows, permissions, STRIDE threat model, CSP, SVG sanitization
7. [`06-infrastructure.md`](06-infrastructure.md) — Azure resources, Bicep module tree, MI matrix, deployment topology
8. [`07-operations.md`](07-operations.md) — CI/CD (GitHub Actions), App Insights wiring, runbooks, DR, secrets rotation
9. [`08-cost-model.md`](08-cost-model.md) — per-operation costs, monthly projections, budget alarms, optimization roadmap
10. [`09-roadmap.md`](09-roadmap.md) — 6 milestones (M0-M6), acceptance gates, sign-off checklist

**Appendices:**

- [`10-decisions.md`](10-decisions.md) — 26 architecture decision records (ADRs)
- [`11-open-questions.md`](11-open-questions.md) — living list of unresolved items

## How to contribute

These are "working docs". Edits come via pull request. Any new ADR:

1. Bump the counter in `10-decisions.md`
2. Use the format: Context · Decision · Consequences · Revisit trigger
3. Link from the relevant requirement if applicable

## Status

| Doc | Status | Last updated |
|---|---|---|
| 00-overview | v1.0 Approved | 2026-04-18 |
| 01-requirements | v1.0 Approved | 2026-04-18 |
| 02-architecture | v1.0 Approved | 2026-04-18 |
| 03-data-model | v1.0 Approved | 2026-04-18 |
| 04-apis | v1.0 Approved | 2026-04-18 |
| 05-security | v1.0 Approved | 2026-04-18 |
| 06-infrastructure | v1.0 Approved | 2026-04-18 |
| 07-operations | v1.0 Approved | 2026-04-18 |
| 08-cost-model | v1.0 Approved | 2026-04-18 |
| 09-roadmap | v1.0 Approved | 2026-04-18 |
| 10-decisions | v1.0 Approved (26 ADRs) | 2026-04-18 |
| 11-open-questions | v1.0 Approved | 2026-04-18 |
