# Contributing to Chapter One

Thanks for your interest. Chapter One is a small, opinionated project maintained by a small group of friends.

## Before you open a PR

1. **Check `docs/phase2/` first.** Major decisions are captured as ADRs in `docs/phase2/10-decisions.md`. If your change contradicts an ADR, either align with the ADR or propose a new ADR in the same PR.
2. **Open an issue first for anything >~50 lines of change.** One-line fixes don't need issues.
3. **Sign your commits** (DCO). Use `git commit -s` — this is instead of a CLA.

## Local setup

See the root `README.md`.

## PR rules

- Target branch: `main`
- CI must be green (`backend-ci`, `frontend-ci`)
- 1 approver required (enforced once team size allows)
- Rebase, don't merge commits
- PR title: `<area>: short verb-first summary` (e.g. `backend: fix citation extractor union`)
- PR body: **why**, not **what** (the diff shows what)

## Code style

- **Backend**: `ruff format` + `ruff check` + `mypy`. All must pass.
- **Frontend**: `prettier` + `eslint`. All must pass.
- **Commits**: present tense imperative ("add foo", not "added foo")

## When your change touches a protected path

`.github/CODEOWNERS` requires a specific reviewer on:
- `/infra/**` — infrastructure
- `/backend/app/auth/**` — authentication
- `/backend/app/debate/**` — debate engine
- `/docs/phase2/10-decisions.md` — ADR additions/changes

## Security

Found a vulnerability? **Do not file a public issue.** Email the maintainer — see GitHub profile.
