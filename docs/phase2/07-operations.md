# Chapter One — Operations

> Scope: CI/CD, observability (Application Insights — set up NOW), deployment runbooks, disaster recovery, secrets rotation.
>
> Out of scope for Phase 2: custom dashboards (deferred, KQL library provided), on-call rotation, paging.

---

## 1. CI/CD — GitHub Actions + Azure

### 1.1 Authentication: OIDC federation (no long-lived secrets)

GitHub Actions authenticates to Azure using **workload identity federation** — no service principal secrets stored in GitHub. Setup steps (one-time):

1. Register an Entra app `co-github-deployer` per environment (dev, prod)
2. Add federated identity credential mapping `repo:<org>/chapter-one:ref:refs/heads/main` (dev) and `repo:<org>/chapter-one:ref:refs/tags/v*` (prod)
3. Grant role assignments (see §1.5)
4. Store `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as GitHub Actions secrets per env

Resulting workflow auth:
```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: azure/login@v2
    with:
      client-id: ${{ secrets.AZURE_CLIENT_ID }}
      tenant-id: ${{ secrets.AZURE_TENANT_ID }}
      subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```

### 1.2 Workflow layout

```
.github/workflows/
├── backend-ci.yml          # lint + test + type-check on every push/PR
├── frontend-ci.yml         # lint + test + build on every push/PR
├── infra-validate.yml      # bicep what-if on PRs touching infra/
├── deploy-dev.yml          # push to main → deploy backend + frontend + infra to dev
├── deploy-prod.yml         # tag v*.*.* → promote to prod (manual approval gate)
└── nightly-db-backup-verify.yml   # restore latest backup into an ephemeral DB, run smoke check
```

### 1.3 Branching and release strategy

| Branch / tag | Triggers | Deploys to |
|---|---|---|
| PR → `main` | backend-ci + frontend-ci + infra-validate | SWA preview env (frontend only) |
| Merge to `main` | deploy-dev | dev |
| Tag `v*.*.*` on `main` | deploy-prod (awaits manual approval) | prod |

Tagging convention: `v{major}.{minor}.{patch}` (SemVer). Release notes auto-generated from PR titles between tags (via Release Drafter).

### 1.4 `deploy-dev.yml` — illustrative shape

```yaml
name: Deploy to dev
on:
  push:
    branches: [main]

concurrency:
  group: deploy-dev
  cancel-in-progress: false

permissions:
  id-token: write
  contents: read

jobs:
  build-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with: { client-id: …, tenant-id: …, subscription-id: … }
      - name: Build + push backend image
        run: |
          IMAGE_TAG=$(git rev-parse --short HEAD)
          az acr build \
            --registry co-dev-acr-cin \
            --image backend:${IMAGE_TAG} \
            --file backend/Dockerfile backend
          echo "IMAGE_TAG=${IMAGE_TAG}" >> $GITHUB_ENV

  build-pdf-worker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
      - run: |
          IMAGE_TAG=$(git rev-parse --short HEAD)
          az acr build \
            --registry co-dev-acr-cin \
            --image pdf-worker:${IMAGE_TAG} \
            --file backend/Dockerfile.pdf backend

  deploy-infra:
    needs: [build-backend, build-pdf-worker]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
      - name: Deploy Bicep
        run: |
          az deployment group create \
            --resource-group co-dev-rg-cin \
            --template-file infra/main.bicep \
            --parameters @infra/envs/dev.parameters.json \
            --parameters imageTag=${{ needs.build-backend.outputs.image_tag }}

  deploy-frontend:
    runs-on: ubuntu-latest
    needs: [deploy-infra]
    steps:
      - uses: actions/checkout@v4
      - uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.SWA_DEV_TOKEN }}
          repo_token: ${{ secrets.GITHUB_TOKEN }}
          app_location: frontend
          output_location: out
          action: upload
```

`deploy-prod.yml` mirrors the shape with:
- Trigger on `push: tags: ['v*.*.*']`
- **`environment: production`** on every job → GitHub requires manual approval from the repo's configured reviewer (you) before each run
- Parameters sourced from `prod.parameters.json`

### 1.5 Required Azure role assignments for the deployer identity

Per env, the federated identity needs:

| Role | Scope | Why |
|---|---|---|
| `Contributor` | Resource group (`co-<env>-rg-cin`) | Create/update resources via Bicep |
| `Key Vault Secrets Officer` | KV | Seed/rotate secrets during deploy |
| `AcrPush` | ACR | Push container images |
| `User Access Administrator` | RG (narrow) | Assign MIs to Container Apps — needed for `az deployment group create` |

Narrow to these specific roles; never assign `Owner`.

### 1.6 Tests gate

- **`backend-ci.yml`**: `pytest`, `ruff check`, `mypy app/` on PRs targeting `main`. Must pass to merge.
- **`frontend-ci.yml`**: `npm run lint`, `npm run test`, `npm run build`. Must pass to merge.
- **`infra-validate.yml`**: `az deployment group what-if` against a throwaway RG. Posts summary comment on the PR.
- Branch protection on `main`: no direct pushes, 1 reviewer required (once contributors join), all CI green required.

### 1.7 Database migrations

Alembic migrations run as a **pre-deploy Container Apps Job** triggered before swapping the API image:

```yaml
  db-migrate:
    needs: [build-backend]
    steps:
      - name: Run alembic upgrade head
        run: |
          az containerapp job execute \
            --name co-dev-job-migrate-cin \
            --resource-group co-dev-rg-cin \
            --image co-dev-acr-cin.azurecr.io/backend:${{ env.IMAGE_TAG }} \
            --args "alembic upgrade head"
```

Failing migration halts the deploy — old API keeps running on old schema until fixed.

---

## 2. Observability — Application Insights (set up NOW)

### 2.1 Why we're wiring this now

Phase 1 used filesystem-based JSONL logs (`logs/{analysis_id}/events.jsonl`). That worked for single-node local dev. In the cloud with:
- Multiple API replicas
- Worker jobs running on separate pods
- Pods that can be killed and replaced
- Users distributed across devices and time

…filesystem logs don't work. Every event needs to land in a central place.

App Insights gives us: full-text search, correlated traces, exception tracking, custom metrics, queryable historical data, alerts.

### 2.2 Architecture

```
[API pod]                         [Worker pod]                   [Cron pod]
   │                                   │                              │
   │  OpenTelemetry exporter           │                              │
   │  (azure-monitor-opentelemetry)    │                              │
   │                                   │                              │
   └──────────────┬────────────────────┴──────────────┬──────────────┘
                  ▼                                   ▼
            ┌─────────────────────────────────────────────────┐
            │  Application Insights                            │
            │  (workspace-based, linked to Log Analytics)      │
            │                                                  │
            │  - requests        (HTTP trace per API call)     │
            │  - dependencies    (LLM calls, Postgres, Blob)   │
            │  - traces          (our structlog + observability│
            │                     events from Phase 1)         │
            │  - customEvents    (pipeline.start, etc.)        │
            │  - exceptions      (with stack)                  │
            │  - customMetrics   (token usage, citation count) │
            └─────────────────────────────────────────────────┘
```

### 2.3 Python integration

Use the **`azure-monitor-opentelemetry`** distro — one-line setup, handles logs + traces + metrics coherently.

```python
# backend/app/observability/azure_monitor.py
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
import logging, os

def init_app_insights() -> None:
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        # local dev: no App Insights wiring, structlog → stdout only
        return
    configure_azure_monitor(
        connection_string=conn,
        logger_name="app",
        instrumentation_options={
            "azure_sdk":  {"enabled": True},
            "django":     {"enabled": False},
            "fastapi":    {"enabled": True},
            "flask":      {"enabled": False},
            "psycopg2":   {"enabled": True},
            "requests":   {"enabled": True},
            "urllib":     {"enabled": True},
            "urllib3":    {"enabled": True},
        },
    )
```

Called once at app startup (`main.py` lifespan) and from worker entrypoints.

### 2.4 Migrating the Phase 1 observability layer

Phase 1's `AnalysisLogger` writes to `events.jsonl` + per-agent `raw/*.json`. Phase 2 adapts:

| Phase 1 | Phase 2 |
|---|---|
| `logger.event("research.query_fired", ...)` | Emit to **both** App Insights (as `customEvent`) **and** Blob (`logs/{analysis_id}/events.jsonl` for manual deep-dive) |
| `logger.save_raw("market_sizing", payload)` | Write to Blob container `raw` at `{analysis_id}/{agent}.json` |
| `build_summary()` for summary.md | Same, written to Blob container `summaries` at `{analysis_id}.md` |

Implementation: a new `AzureMonitorSink` adapter sits next to the existing file sink. Both emit in parallel.

```python
class AzureMonitorSink:
    def event(self, event_type: str, **fields):
        tracer = trace.get_tracer("chapterone")
        with tracer.start_as_current_span(event_type) as span:
            for k, v in fields.items():
                if not _is_pii_field(k):
                    span.set_attribute(k, _stringify(v))
```

### 2.5 What gets logged (same events as Phase 1, preserved)

| Event | Category in App Insights |
|---|---|
| `pipeline.start` / `pipeline.complete` / `pipeline.error` | `customEvent` |
| `agent.start` / `agent.complete` / `agent.error` | `customEvent` + parent span on `requests` |
| `llm.request` / `llm.response` / `llm.fallback` | `dependency` (treated as outbound call) |
| `research.plan` / `query_start` / `query_fired` / `query_error` | `customEvent` |
| `research.coverage` / `coverage_warning` | `customEvent` |
| `research.citations` / `research.quality` / `staleness_warning` | `customEvent` |
| `render.mermaid_error` (from frontend telemetry) | `customEvent` |
| `chart.rendered` / `chart.sanitizer_applied` | `customEvent` |
| Exceptions (unhandled) | `exception` |
| HTTP requests | `request` (auto-captured) |
| Postgres queries | `dependency` (auto-captured) |

### 2.6 PII redaction

OpenTelemetry span processor strips these fields before export:
- `idea_text` (unless `LOG_IDEA_TEXT=true`)
- `email`
- `raw_prompt`, `raw_response` (stay in Blob, not telemetry)
- Request bodies on mutation endpoints

Implemented as a custom `SpanProcessor` that walks `span.attributes` and removes/hashes based on a denylist.

### 2.7 Sampling & retention

- **Sampling**: OFF at our scale (5 users). Keep every event.
- **Retention**: 30 days (configured on Log Analytics workspace; reduces cost)
- **Cap**: Daily data cap of 1GB per env as safety net (Log Analytics setting)

### 2.8 KQL query library (pin these when ready to build dashboards)

```kql
// 1. Analyses per day, success vs failure
customEvents
| where name in ("pipeline.start", "pipeline.complete", "pipeline.error")
| summarize
    started  = countif(name == "pipeline.start"),
    completed = countif(name == "pipeline.complete"),
    errored  = countif(name == "pipeline.error")
  by bin(timestamp, 1d)

// 2. Research quality over time
customEvents
| where name == "research.citations"
| extend agent = tostring(customDimensions.agent)
| summarize
    avg_urls = avg(toint(customDimensions.citation_count)),
    avg_unique_domains = avg(toint(customDimensions.unique_domains))
  by agent, bin(timestamp, 1d)

// 3. Top failing agents
customEvents
| where name == "agent.error"
| summarize errors = count() by tostring(customDimensions.agent)
| order by errors desc

// 4. LLM token spend per day
customEvents
| where name == "llm.response"
| extend
    tokens_in = toint(customDimensions.input_tokens),
    tokens_out = toint(customDimensions.output_tokens)
| summarize
    total_in = sum(tokens_in),
    total_out = sum(tokens_out),
    estimated_inr = sum(tokens_in * 0.00000175 * 85 + tokens_out * 0.000014 * 85)
  by bin(timestamp, 1d)

// 5. Debate usage
customEvents
| where name == "debate.turn_completed"
| summarize turns = count() by tostring(customDimensions.analysis_id)
| top 10 by turns

// 6. Slow analyses
customEvents
| where name == "pipeline.complete"
| extend duration_s = toint(customDimensions.duration_ms) / 1000
| where duration_s > 300
| project timestamp, duration_s, customDimensions.verdict

// 7. Staleness warnings (research quality regression)
customEvents
| where name == "research.staleness_warning"
| summarize count() by tostring(customDimensions.agent), bin(timestamp, 1d)
```

### 2.9 Alerts (email Hemanth — no paging)

Azure Monitor alert rules configured via Bicep:

| Alert | Condition | Severity | Action |
|---|---|---|---|
| Error rate | `requests | where success == false` > 5% over 5 min | 2 (warning) | Email |
| Analysis failures | `customEvents | where name == "pipeline.error"` >3 in 1hr | 2 | Email |
| Monthly cost | Resource group spend > 75% of ₹12,500 | 3 (info) | Email |
| Monthly cost | > 90% | 1 (critical) | Email + SMS (optional, not yet) |
| AI Foundry rate limits | `customEvents | where name == "llm.error" and customDimensions.status_code == 429` > 10 in 10min | 3 | Email |
| DB connections | > 80% of Postgres B1ms cap (100 conns) | 2 | Email |

Email goes to `hemanththota@microsoft.com`. That's the entire on-call system for Phase 2.

### 2.10 Dashboards (deferred)

Not built in Phase 2. When ready:
- Create an Azure Workbook templated from the KQL queries above
- Pin the 3-4 most useful queries: analyses/day, quality trend, token spend, error rate
- Save workbook in the resource group — team can view in Azure Portal

No Grafana, no PowerBI, no Datadog in Phase 2.

---

## 3. Deployment runbooks

### 3.1 Initial bootstrap (one-time per env)

```bash
# 1. Create resource group
az group create -n co-prod-rg-cin -l centralindia

# 2. Provision Entra External ID tenant manually via portal
#    (Bicep support limited; one-time setup)

# 3. Deploy full infra
az deployment group create \
  --resource-group co-prod-rg-cin \
  --template-file infra/main.bicep \
  --parameters @infra/envs/prod.parameters.json

# 4. Seed secrets that can't be generated in Bicep
az keyvault secret set --vault-name co-prod-kv-cin-01 --name azure-openai-api-key --value '<secret>'
az keyvault secret set --vault-name co-prod-kv-cin-01 --name google-oauth-client-secret --value '<secret>'

# 5. Build + push first backend image
az acr build --registry coprodcrcin --image backend:bootstrap backend/

# 6. Update Container App to use bootstrap image
az containerapp update -n co-prod-api-cin -g co-prod-rg-cin \
  --image coprodcrcin.azurecr.io/backend:bootstrap

# 7. Run initial DB migration
az containerapp job start -n co-prod-job-migrate-cin -g co-prod-rg-cin

# 8. Deploy frontend (via GitHub Actions on first push to main)

# 9. Verify
curl https://co-prod-api-cin.<unique>.centralindia.azurecontainerapps.io/health
```

Apply CanNotDelete lock after bootstrap:
```bash
az lock create --name co-prod-lock --lock-type CanNotDelete \
  --resource-group co-prod-rg-cin
```

### 3.2 Routine deploy

Entirely automated via GitHub Actions. To deploy to prod:

```bash
# On main with fresh green CI:
git tag v0.3.0
git push origin v0.3.0
# GitHub Action waits for manual approval
# Navigate to GitHub → Actions → Approve the pending workflow
# Action completes in ~6 min
```

### 3.3 Rollback

The Container App keeps the last 10 revisions. To roll back the backend:

```bash
# List revisions
az containerapp revision list -n co-prod-api-cin -g co-prod-rg-cin \
  -o table

# Set traffic back to a prior revision
az containerapp ingress traffic set -n co-prod-api-cin -g co-prod-rg-cin \
  --revision-weight <prior-revision-name>=100
```

Frontend rollback: re-run the Static Web Apps deploy action targeting the prior commit SHA.

DB migrations are forward-only; if a migration is bad, write a compensating migration. Never `alembic downgrade` in prod.

### 3.4 Emergency stop

If something is actively compromising users:

```bash
# 1. Stop accepting new analyses (soft)
az containerapp update -n co-prod-api-cin -g co-prod-rg-cin \
  --set-env-vars FEATURE_ANALYSES_ENABLED=false

# 2. If needed, kill all traffic (hard)
az containerapp ingress disable -n co-prod-api-cin -g co-prod-rg-cin

# 3. Revoke all sessions
# (run SQL)
UPDATE sessions SET expires_at = NOW() WHERE expires_at > NOW();

# 4. Rotate all Key Vault secrets
for secret in $(az keyvault secret list --vault-name co-prod-kv-cin-01 --query '[].name' -o tsv); do
    az keyvault secret set --vault-name co-prod-kv-cin-01 --name $secret --value "$(openssl rand -hex 32)"
done
```

---

## 4. Disaster recovery

### 4.1 Scenarios & recovery

| Scenario | RPO | RTO | Procedure |
|---|---|---|---|
| Bad deploy | 0 | 10 min | Rollback (§3.3) |
| Corrupt migration | 0 | 1-2 hr | Write compensating migration; redeploy; in worst case restore DB to pre-migration backup |
| Postgres instance down | 24h (daily backup) | 2-4 hr | Point-in-time restore to new server; update `DATABASE_URL` secret; redeploy |
| Blob data loss | 0 (LRS is single-region durable) | N/A | Rare; customer-managed GRS upgrade deferred |
| Central India region outage | 24h | Best-effort | Wait for Azure to restore; restore from backups to a different region if multi-day |
| Key Vault compromised | 0 | 2-6 hr | Rotate every secret (§3.4 emergency stop), audit App Insights for anomalies |
| Accidental `DROP TABLE` | 24h | 1-2 hr | Point-in-time restore (7-day PITR retention on Flexible Server) |

### 4.2 Backup verification

Nightly workflow `.github/workflows/nightly-db-backup-verify.yml`:
- Restore latest Postgres backup to an ephemeral server
- Connect + run `SELECT COUNT(*) FROM users, analyses, comments`
- If row counts are zero (restore failed) → alert
- Tear down ephemeral server

This way we know backups are actually usable, not just "being created".

---

## 5. Secrets rotation

All secrets in Key Vault are **versioned** — rotations push a new version without breaking existing pods (they pick up at restart).

### 5.1 Rotation schedule

| Secret | Frequency | Method |
|---|---|---|
| `azure-openai-api-key` | 90 days | Portal/CLI on AI Foundry → update KV |
| `postgres-app-password` | 90 days | `ALTER ROLE app PASSWORD 'new'` → update KV |
| `google-oauth-client-secret` | 180 days | Google Cloud Console → update KV |
| `session-encryption-key` | 180 days with overlap | See §5.2 rolling key rotation |
| `service-bus-sas-connection` | 90 days | Regenerate on namespace → update KV |
| `blob-sas-signing-key` | 90 days | Regenerate on storage account → update KV |

### 5.2 Session key rolling rotation

Session cookies are Fernet-encrypted. To rotate without logging everyone out:

1. New key generated, added to `session-encryption-keys` (multi-value secret — array)
2. Pods pick up on restart; use **MultiFernet** to decrypt with either old or new
3. All new sessions signed with new key
4. After 30 days (max session age), remove old key from the array

### 5.3 Secret access logs

Key Vault logs every secret read to Log Analytics. KQL query to audit:
```kql
AzureDiagnostics
| where ResourceType == "VAULTS"
| where OperationName == "SecretGet"
| project TimeGenerated, identity_name_s, properties_s
```

---

## 6. Environments & promotion

- **dev**: auto-deploys on every `main` push; data is disposable; can be wiped/rebuilt
- **prod**: deploys on `v*.*.*` tag with manual approval; data is sacred

### 6.1 Config drift prevention

`infra/main.bicep` is the single source of truth. Manual portal changes are **not allowed** — if a fix is made via CLI/portal to unblock, a corresponding Bicep change must land in the same PR.

Monthly: a scheduled workflow runs `az deployment group what-if` against prod and alerts if drift is detected.

---

## 7. Contributing (for future friends)

When we open the repo:

- `CONTRIBUTING.md` at root explains: how to run locally, how to write a test, how PRs work
- `CODEOWNERS` at `.github/CODEOWNERS`:
  ```
  /infra/            @hemanth
  /backend/app/auth/ @hemanth
  /backend/app/debate/ @hemanth
  /docs/phase2/10-decisions.md @hemanth
  # everything else: anyone can review
  ```
- First-time contributors sign the **DCO** (Developer Certificate of Origin) via commit sign-off (`git commit -s`); no CLA needed for MIT
- PR template checks: tests added, ADR updated if decisions changed

---

## 8. What's deliberately missing from Phase 2 ops

Documented here so it doesn't feel ignored:

- ❌ **Custom dashboards** — KQL library provided; pin when you want
- ❌ **On-call rotation / paging** — email-only alerts
- ❌ **Synthetic monitoring** (uptime pings) — Azure Monitor availability tests can be added in 20 minutes if desired
- ❌ **Multi-region active/active** — deferred
- ❌ **Automated backup restore testing** — covered by nightly verify
- ❌ **Chaos engineering** — not for 5 users
- ❌ **Feature flags service** — env vars are enough for Phase 2
- ❌ **Blue/green deployments** — Container Apps rolling update is sufficient

All revisitable in Phase 3 if adoption grows.
