# GitHub Actions workflows

| File | Trigger | Purpose |
|---|---|---|
| `backend-ci.yml` | push, PR | Lint, type-check, test the Python backend |
| `frontend-ci.yml` | push, PR | Lint, test, build the Next.js frontend |
| `infra-validate.yml` | PR touching `infra/**` | `az deployment what-if` — safe preview of infra changes |
| `deploy-dev.yml` | push to `main` | Build image → push to ACR → deploy to dev env |
| `deploy-prod.yml` | tag `v*.*.*` | Deploy to prod (manual approval) |
| `nightly-db-backup-verify.yml` | cron 03:00 UTC | Restore latest backup, smoke test, tear down |

See `docs/phase2/07-operations.md` §1 for full details.

**All workflows use OIDC federation to Azure — no long-lived secrets.**
