# Chapter One — Infrastructure (Azure + Bicep)

> IaC tool: **Bicep** (ADR-015). Modules live under `infra/modules/`; environment parameter files under `infra/envs/`.
> Region: **Central India** (primary); Azure AI Foundry stays on its existing region.

---

## 1. Resource naming convention

All resources follow `co-{env}-{purpose}-{region-code}-{suffix?}`:

- `co` = Chapter One
- `env` = `dev` | `prod`
- `purpose` = short identifier (`api`, `worker`, `pg`, `sb`, `kv`, `blob`, `log`, `ai`)
- `region-code` = `cin` (Central India), `eus2` (East US 2), etc.
- `suffix` = optional for disambiguation

Examples:
- `co-prod-api-cin` — Container App hosting the backend API
- `co-dev-pg-cin` — Postgres Flexible Server for dev
- `co-prod-kv-cin-01` — Key Vault (suffix reserves space for future splits)
- `cocinprodblob01` — Storage account (no dashes, ≤24 chars, globally unique; adapt convention)

## 2. Full resource inventory (prod)

| Azure service | Resource name | SKU | Purpose |
|---|---|---|---|
| Resource group | `co-prod-rg-cin` | — | Container for all prod resources |
| Virtual Network | `co-prod-vnet-cin` | Basic, /22 address space | Isolate Postgres + Container Apps env |
| Container Apps Environment | `co-prod-cae-cin` | Workload profiles (Consumption) | Hosts backend API + worker jobs |
| Container App (API) | `co-prod-api-cin` | 1-3 replicas, 0.5 vCPU / 1 GiB each | Backend HTTP + SSE |
| Container Apps Job (Analysis Worker) | `co-prod-worker-analysis-cin` | 1 vCPU / 2 GiB, scale on queue | Runs pipeline |
| Container Apps Job (PDF) | `co-prod-worker-pdf-cin` | 1 vCPU / 2 GiB, event-triggered | Playwright render |
| Container Apps Job (Cron) | `co-prod-worker-cron-cin` | 0.25 vCPU / 0.5 GiB, scheduled | Notifications + streak cleanup |
| Azure Container Registry | `coprodcrcin` | Basic | Holds backend + worker images |
| Postgres Flexible Server | `co-prod-pg-cin` | Burstable B1ms, 32 GiB storage, HA off | Relational data |
| Storage account | `coprodblob01cin` | Standard LRS | Blob storage (avatars, PDFs, raw JSON, summaries) |
| Service Bus namespace | `co-prod-sb-cin` | Standard | `analyses.submitted` queue + future topics |
| Key Vault | `co-prod-kv-cin-01` | Standard | Secrets |
| Log Analytics workspace | `co-prod-log-cin` | Pay-as-you-go, 30-day retention | Centralised logs |
| Application Insights | `co-prod-ai-cin` | Workspace-based, linked to above | APM + traces |
| Azure Monitor alerts | `co-prod-alerts-*` | — | Cost cap, error rate, availability |
| Static Web App | `co-prod-web` | Standard (for custom domain later; Free for MVP) | Frontend |
| Entra External ID tenant | `chapterone-prod.onmicrosoft.com` | Free tier (50K MAU) | User directory |

Dev mirrors prod with these downgrades:
- Container App API: 0-1 replicas, scale to zero when idle
- Postgres: Burstable B1ms (same — can't go smaller) but smaller storage (8 GiB)
- No Azure Monitor alerts
- Cheaper/shorter Log Analytics retention (14 days)

## 3. Bicep module tree

```
infra/
├── main.bicep                       # top-level; imports modules; orchestrates per-env deployment
├── envs/
│   ├── dev.parameters.json
│   └── prod.parameters.json
├── modules/
│   ├── network.bicep                # VNet + subnets (container-apps, pg, pvt-endpoints)
│   ├── container-apps-env.bicep     # CAE + log analytics linkage
│   ├── container-app-api.bicep      # backend API app + ingress + ACR pull
│   ├── container-app-job.bicep      # generic job template (parameterised for analysis/pdf/cron)
│   ├── postgres.bicep               # Flexible Server + firewall + database
│   ├── storage.bicep                # storage account + containers (avatars, pdfs, raw, summaries)
│   ├── service-bus.bicep            # namespace + queue + topics
│   ├── key-vault.bicep              # KV + access policies / RBAC
│   ├── acr.bicep                    # container registry
│   ├── monitor.bicep                # Log Analytics + App Insights + alerts
│   ├── static-web-app.bicep         # SWA + custom domain placeholder
│   └── identity.bicep               # managed identity + role assignments
└── scripts/
    ├── deploy-dev.sh                # wrapper around `az deployment group create`
    ├── deploy-prod.sh
    └── teardown.sh                  # safe teardown for dev (preserves prod)
```

## 4. Module interfaces (parameter shapes)

Sketches only — precise types in the actual Bicep files.

### `main.bicep`
```bicep
param env string                           // 'dev' | 'prod'
param location string = 'centralindia'
param aiFoundryEndpoint string             // existing foundry endpoint URL
@secure()
param aiFoundryApiKey string               // passed in at deploy time, stored immediately in KV
param googleOAuthClientId string
@secure()
param googleOAuthClientSecret string

// Calls each module, wires outputs → inputs
```

### `network.bicep`
```bicep
param env string
param location string
param vnetAddressSpace string = '10.10.0.0/22'
param subnetContainerApps string = '10.10.0.0/23'   // /23 required by CAE
param subnetPostgres string = '10.10.2.0/27'
param subnetPrivateEndpoints string = '10.10.2.32/27'
output vnetId string
output subnetContainerAppsId string
output subnetPostgresId string
```

### `container-app-api.bicep`
```bicep
param name string
param environmentId string
param acrLoginServer string
param managedIdentityId string
param imageTag string                      // comes from CI (git SHA)
param keyVaultName string                  // for secret refs
param minReplicas int = 1
param maxReplicas int = 3
param envVars object                       // non-secret env

// Exposes ingress on 8000, HTTPS-only, managed cert
// Uses secretRef: keyvault:// URIs for sensitive vars
output fqdn string
```

### `postgres.bicep`
```bicep
param name string
param location string
param sku object = { tier: 'Burstable', name: 'Standard_B1ms' }
param storageGB int = 32
param pgAdminPassword string @secure()
param subnetId string                      // VNet-injected
output fqdn string
output resourceId string
```

### `service-bus.bicep`
```bicep
param namespaceName string
param queues array = ['analyses.submitted', 'analyses.submitted.deadletter']
param topics array = []                    // reserved for Phase 3
output namespaceEndpoint string
```

### `storage.bicep`
```bicep
param name string
param location string
param containers array = [
  { name: 'avatars', publicAccess: 'Blob' }    // blobs readable; no listing
  { name: 'pdfs',    publicAccess: 'None' }    // signed URL access only
  { name: 'raw',     publicAccess: 'None' }
  { name: 'summaries', publicAccess: 'None' }
]
output accountName string
output primaryEndpoint string
```

### `key-vault.bicep`
```bicep
param name string
param tenantId string
param readerIdentities array               // list of principal IDs that get Secrets User role
output vaultUri string
```

### `identity.bicep`
Creates one system-assigned identity per runtime component. Role assignments:
- API identity: Key Vault Secrets User + Service Bus Data Sender + Storage Blob Data Contributor + ACR Pull + (Postgres via managed identity auth)
- Worker identity: same as API + Service Bus Data Receiver
- PDF worker identity: Storage Blob Data Contributor (pdfs container)
- Cron identity: Postgres access only (no queue/storage)

## 5. Managed Identity matrix

| Identity | Roles | Scope |
|---|---|---|
| `api-mi` | Key Vault Secrets User | `co-prod-kv-cin-01` |
| | Azure Service Bus Data Sender | `co-prod-sb-cin` |
| | Storage Blob Data Contributor | `coprodblob01cin` (all containers) |
| | ACR Pull | `coprodcrcin` |
| `worker-analysis-mi` | Key Vault Secrets User | `co-prod-kv-cin-01` |
| | Azure Service Bus Data Receiver | `co-prod-sb-cin/queues/analyses.submitted` |
| | Storage Blob Data Contributor | `coprodblob01cin/raw,summaries` |
| | AI Foundry Developer | Foundry resource |
| `worker-pdf-mi` | Key Vault Secrets User | `co-prod-kv-cin-01` |
| | Storage Blob Data Contributor | `coprodblob01cin/pdfs` |
| `worker-cron-mi` | Key Vault Secrets User | `co-prod-kv-cin-01` |

Postgres connections use **Entra auth** where possible (passwordless via managed identity); password fallback stored in KV.

## 6. Deployment topology

```
                        ┌──────────────────────────┐
                        │  Azure Static Web Apps    │     (frontend, global CDN)
                        │  co-prod-web              │
                        └────────────┬──────────────┘
                                     │  HTTPS
                                     ▼
                        ┌──────────────────────────┐
                        │  Container Apps Ingress  │
                        │  (managed TLS)           │
                        └────────────┬─────────────┘
                                     │
        ┌────────────────────────────▼────────────────────────────────┐
        │               Container Apps Environment                   │
        │               co-prod-cae-cin  (VNet injected)             │
        │                                                            │
        │   ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐ │
        │   │              │  │                  │  │              │ │
        │   │ API          │  │ Analysis worker  │  │ PDF worker   │ │
        │   │ (always-on)  │  │ (queue-triggered)│  │ (event)      │ │
        │   │              │  │                  │  │              │ │
        │   └──────┬───────┘  └─────────┬────────┘  └──────┬───────┘ │
        │          │                     │                  │         │
        │          │                 ┌───▼────┐             │         │
        │          │                 │  Cron  │             │         │
        │          │                 │ worker │             │         │
        │          │                 └────────┘             │         │
        │                                                             │
        └─────┬──────────────┬──────────────┬──────────────┬──────────┘
              │              │              │              │
              ▼              ▼              ▼              ▼
         Postgres        Service Bus     Blob          Key Vault
         (VNet-pvt)      (public+SAS)   (public+SAS)  (public+MSI)
              │              │              │              │
              └─▶ App Insights / Log Analytics  ◀──────────┘

        Cross-region:  API + worker-analysis ──────▶ Azure AI Foundry
                                                    (existing resource,
                                                     likely East US 2)
```

Key properties:
- Container Apps Env **VNet-injected** so Postgres can be private (not publicly reachable)
- Blob + Key Vault reached via public endpoints + managed identity auth (simpler than private endpoints for Phase 2; revisit if sensitive compliance needed)
- Service Bus via connection string stored in KV (could use MSI but SBus MSI support has quirks; connection string is fine)

## 7. Environment variables plumbing

Each Container App / Job receives these at boot time via Bicep:

```bash
# Non-secret
AZURE_OPENAI_ENDPOINT=https://testingclaudecode.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2025-03-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-5.3-chat
DATABASE_URL=postgres://api@co-prod-pg-cin:5432/chapterone?sslmode=require   # Entra auth or password-via-KV
REDIS_URL=  # empty in Phase 2
LOG_DIR=/tmp/logs  # per-pod scratch; raw JSON goes to Blob
LOG_RAW_RESPONSES=true
LOG_IDEA_TEXT=false
RESEARCH_CONCURRENCY=4
CORS_ORIGINS=https://co-prod-web.azurestaticapps.net
SERVICE_BUS_NAMESPACE=co-prod-sb-cin.servicebus.windows.net
SERVICE_BUS_QUEUE_ANALYSES=analyses.submitted
BLOB_ACCOUNT_URL=https://coprodblob01cin.blob.core.windows.net
APPLICATIONINSIGHTS_CONNECTION_STRING=  # from KV reference

# Secrets (Container App pulls these via secretRef → KV)
AZURE_OPENAI_API_KEY=@Microsoft.KeyVault(VaultName=...;SecretName=azure-openai-api-key)
POSTGRES_PASSWORD=@Microsoft.KeyVault(...)
SESSION_ENCRYPTION_KEY=@Microsoft.KeyVault(...)
GOOGLE_OAUTH_CLIENT_SECRET=@Microsoft.KeyVault(...)
SERVICE_BUS_SAS_CONNECTION=@Microsoft.KeyVault(...)
```

## 8. Custom domain (deferred)

Phase 2 ships on Azure default subdomains:
- Frontend: `https://<hash>.azurestaticapps.net`
- Backend: `https://co-prod-api-cin.<unique>.centralindia.azurecontainerapps.io`

Custom domain (e.g. `chapterone.app`) + SWA custom domain + Container Apps custom domain:
- Domain registration: not in Phase 2
- DNS: Azure DNS zone when ready
- TLS: managed certs on both SWA and Container Apps

## 9. Per-environment differences

| Setting | Dev | Prod |
|---|---|---|
| API replicas | 0-1 (scale to zero) | 1-3 |
| Analysis worker parallel replicas | 1 | 3 (SBus scale rule) |
| Postgres storage | 8 GiB | 32 GiB |
| Log Analytics retention | 14 days | 30 days |
| Azure Monitor alerts | none | cost, errors, availability |
| Entra External ID tenant | `chapterone-dev.onmicrosoft.com` | `chapterone-prod.onmicrosoft.com` |
| Feature flags (future) | all flags ON | subset ON |

## 10. Bootstrap procedure (one-time)

1. Create prod resource group manually: `az group create -n co-prod-rg-cin -l centralindia`
2. Deploy Entra External ID tenants (manual via portal — Bicep support limited)
3. `az deployment group create -g co-prod-rg-cin -f infra/main.bicep -p infra/envs/prod.parameters.json`
4. Build + push initial backend image to ACR
5. Update Container App with new image tag
6. Build + deploy frontend via SWA's GitHub integration

Subsequent deploys are done via GitHub Actions (see `07-operations.md`, Round 5).

## 11. Cost estimate (prod, steady state)

| Item | Monthly |
|---|---|
| Container Apps (API always-on + jobs active ~2h/day) | ₹2,500 - 3,500 |
| Postgres Flexible Server B1ms + 32GB | ₹2,800 |
| Blob Storage (few GB, minimal ops) | ₹100 |
| Service Bus Standard | ₹500 |
| Key Vault | ₹100 |
| Log Analytics + App Insights (30-day retention, low volume) | ₹500 - 1,000 |
| ACR Basic | ₹350 |
| Static Web Apps | **Free** |
| Entra External ID (5 MAU) | **Free** |
| Azure AI Foundry — gpt-5.3-chat (est. 100 analyses/mo × ₹10) | ₹1,000 |
| Azure AI Foundry — web_search tool (~200 calls/mo × ₹2) | ₹400 |
| Playwright PDF renders (few GB CPU-min) | ₹50 |
| Egress (India → East US 2 for LLM calls) | ₹200 |
| **Total** | **~₹8,500 / mo** |
| **Cap** | **₹12,500 / mo (VS Enterprise)** |
| **Headroom** | **~₹4,000 / mo** |

Dev env runs ~30% of prod cost because consumption plans idle. Combined dev+prod: ~₹11,000/mo. Still under cap.

## 12. Teardown

Dev can be torn down and rebuilt trivially:
```bash
az group delete -n co-dev-rg-cin --yes
az deployment group create -g co-dev-rg-cin -f infra/main.bicep -p infra/envs/dev.parameters.json
```
Data in dev is disposable. Prod has `CanNotDelete` resource lock on the resource group to prevent accidents.

## 13. Disaster recovery (MVP scope)

- **RPO (data loss window)**: 24h — daily Postgres automated backup
- **RTO (recovery time)**: best-effort ~4h — restore DB to new server, redeploy via Bicep, swap DNS
- **Blob DR**: LRS (locally redundant) only; regional outage = data at risk. Acceptable for MVP. Revisit with GRS at Phase 3.
- **Runbook**: to be written in `07-operations.md`
