# Chapter One — Cost Model

> Per-operation cost breakdown, monthly projections at different scales, cost control mechanisms, optimization roadmap.
> Currency: **INR (₹)**. All figures estimates based on Azure India pricing (Feb 2026) and actual Phase 1 telemetry.

---

## 1. Per-operation costs

### 1.1 One analysis (end-to-end)

Using Phase 1 instrumented data (avg across runs in `backend/logs/efc096a3-*`):

| Cost component | Amount per analysis | Notes |
|---|---|---|
| `gpt-5.3-chat` input tokens (~300K) | ₹45 | $1.75/1M × 85 INR/USD × 300K = ₹44.6 |
| `gpt-5.3-chat` output tokens (~18K) | ₹21 | $14/1M × 85 × 18K = ₹21.4 |
| Azure AI Foundry web_search calls (~22) | ~₹0 | Bundled with Responses API at our volume |
| Container Apps compute (3 min × 1 vCPU) | ₹1.5 | $0.000024/vCPU-s × 85 × 180s = ₹0.4 (small) |
| Postgres writes (~80 rows) | ₹0.05 | negligible |
| Blob writes (~11 raw JSON files, ~200 KB) | ₹0.02 | negligible |
| Service Bus message (enqueue + consume) | ₹0.01 | negligible |
| App Insights telemetry (~150 events) | ₹0.3 | ~300 KB ingested |
| **Total per analysis** | **~₹68** | |

Round off: **₹70 per analysis**. Most of this is LLM cost.

### 1.2 One debate turn

A debate turn = 1 grounded LLM call + optional live web_search + retrieval from stored research.

| Component | Cost |
|---|---|
| Retrieval from stored research (keyword match, no LLM) | ₹0 |
| Live web_search (0-1 per turn) | ~₹0.5 |
| LLM call: ~20K input tokens (report + thread) + 1K output | ₹4.2 |
| **Total per turn** | **~₹5** |

A typical 10-turn debate: **~₹50**. An active debate (20+ turns): ~₹100.

### 1.3 Patch-accept (section regeneration)

Accepting a patch triggers re-running the target agent + dependents:

| Section touched | Agents re-run | Cost |
|---|---|---|
| `dim_1_problem` (cheap) | problem_pmf only | ~₹3 |
| `dim_5_moat` (cascades) | risk_moat + scoring + report_compiler | ~₹12 |
| `market_size` (cascades heavily) | market_sizing synthesis + business_model + scoring + compiler | ~₹18 |
| `competitive_landscape` | competitive_intel synthesis + scoring + compiler | ~₹15 |

Average: **~₹10 per accepted patch**.

### 1.4 PDF render

- Playwright spin-up: ~3s CPU (Container Apps Job) → ~₹0.01
- Blob write (PDF ~1-3 MB) → ₹0.02
- Cached on subsequent downloads of the same version → free

**~₹0.03 per fresh PDF, effectively free on cache hit.**

### 1.5 Profile / feed / comments

Pure HTTP + Postgres reads. **Essentially free** (₹0.001 per page view range).

---

## 2. Monthly projections

### 2.1 Today (5 active users, realistic usage)

| Assumption | Value |
|---|---|
| Users | 5 |
| Analyses / user / week | 3 |
| Debate turns / analysis (avg) | 2 |
| Accepted patches / analysis | 0.3 |
| PDF downloads / analysis | 1 |

Monthly volume:
- Analyses: 5 × 3 × 4.3 = **~65 / month**
- Debate turns: 65 × 2 = **~130**
- Accepted patches: **~20**
- PDFs: **~65**

Cost:
| Line item | Monthly |
|---|---|
| Analyses (65 × ₹70) | ₹4,550 |
| Debate turns (130 × ₹5) | ₹650 |
| Accepted patches (20 × ₹10) | ₹200 |
| PDFs (65 × ₹0.03) | ₹2 |
| **Variable LLM cost** | **~₹5,400** |
| **Fixed infra (from §3 below)** | **~₹6,650** |
| **Total prod** | **~₹12,050** |

**Inside ₹12,500 cap with ~₹450 margin.**

### 2.2 Growth scenarios

| Scenario | Users | Analyses/mo | Variable | Fixed | Total/mo |
|---|---|---|---|---|---|
| Friends MVP (today) | 5 | 65 | ₹5,400 | ₹6,650 | **₹12,050** |
| Small circle | 20 | 250 | ₹20,500 | ₹7,000 | **₹27,500** |
| Extended (invite-only) | 100 | 1,200 | ₹97,000 | ₹12,000 | **₹109,000** |
| Public launch | 500 | 5,000 | ₹405,000 | ₹45,000 | **₹450,000** |

At 20+ users the VS Enterprise credit is insufficient. The product needs monetization OR cost reduction before growing past the friend circle.

### 2.3 Fixed infra breakdown (combined dev + prod)

| Resource | Monthly (₹) |
|---|---|
| Container Apps (prod API always-on + occasional jobs) | 2,800 |
| Container Apps (dev, scaled to zero) | 200 |
| Postgres Flexible Server B1ms × 2 (prod 32GB, dev 8GB) | 4,000 |
| Blob Storage (5-10 GB hot) | 150 |
| Service Bus Standard × 2 | 800 |
| Key Vault × 2 | 150 |
| Log Analytics + App Insights (30-day prod, 14-day dev) | 1,200 |
| ACR Basic | 350 |
| Static Web Apps × 2 | 0 (free tier) |
| Entra External ID | 0 (free tier) |
| Egress (India → LLM region) | 200 |
| **Combined fixed** | **~₹9,850 / mo** |

(Earlier I estimated ₹11,000 combined total in `06-infrastructure.md`; that included the variable LLM portion. Fixed-only is ₹9,850 for dev+prod together.)

---

## 3. Cost control mechanisms

### 3.1 Budget alerts (Azure Cost Management — Bicep-provisioned)

```bicep
resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'co-prod-budget-monthly'
  properties: {
    category: 'Cost'
    amount: 12500
    timeGrain: 'Monthly'
    notifications: {
      '50_percent': { enabled: true, operator: 'GreaterThan', threshold: 50, contactEmails: ['hemanththota@microsoft.com'] }
      '75_percent': { enabled: true, operator: 'GreaterThan', threshold: 75, contactEmails: ['hemanththota@microsoft.com'] }
      '90_percent': { enabled: true, operator: 'GreaterThan', threshold: 90, contactEmails: ['hemanththota@microsoft.com'] }
      'forecast':   { enabled: true, operator: 'GreaterThan', threshold: 100, thresholdType: 'Forecasted', contactEmails: ['hemanththota@microsoft.com'] }
    }
  }
}
```

### 3.2 Per-user soft caps (Phase 3 when rate limits go live)

Not enforced in Phase 2 but design-ready:

| Metric | Soft cap |
|---|---|
| Analyses per user per day | 20 |
| Debate turns per user per report per day | 30 |
| Accepted patches per report per day | 5 |
| PDF downloads per user per hour | 60 |

### 3.3 VS Enterprise subscription behaviour at cap

Visual Studio Enterprise subscription has a **hard stop**: once monthly credits are exhausted, Azure **disables** paid services (unless you enable pay-as-you-go overflow).

Effect on Chapter One:
- Container Apps suspends (users get 503 on API)
- Postgres stays up but read-only after hard stop (Azure's own behaviour)
- Static Web Apps keeps running (free tier)
- Entra External ID keeps working (free tier)

**This is a feature, not a bug.** Cap can't be breached silently. Hemanth will get the 90% alert email before it trips.

---

## 4. Optimizations — roadmap (deferred)

Not for Phase 2, but things to unlock cheaper ops later:

### 4.1 Free or cheap now
- ✅ **PDF caching by version_id** — done by design
- ✅ **Service Bus scale-to-zero on worker jobs** — done by design
- ✅ **LOG_RAW_RESPONSES toggle** — can flip off if Blob costs grow

### 4.2 Cheap in Phase 3
- **Switch analysis agents to `gpt-5.3-chat` only for high-impact steps** — cheaper sibling models (gpt-5.3-mini if available) for orchestrator + regulatory agents could cut LLM cost 30%
- **Postgres query cache for feed** — Redis Cache adds ₹500/mo; feed response time drops <100ms, fewer DB queries
- **Agent output compression** — store per-agent JSON gzip'd in Blob, ~5× smaller

### 4.3 Costlier but material
- **Switch web_search to Serper.dev** (~$50/mo = ₹4,250/mo) — quality uplift + Google SERPs. Net +cost, but quality is the Phase 2 loss-leader.
- **Reserved capacity on Postgres** (1 year commit) — ~30% off the B1ms rate. Only worth it when we're confident in usage.
- **Azure Front Door** — ~₹2,500/mo, saves egress + adds global latency wins. Phase 4.

---

## 5. Cost-per-user analytics (later)

App Insights query to attribute cost to users (Phase 3):
```kql
customEvents
| where name == "llm.response"
| extend
    user_id = tostring(customDimensions.owner_user_id),
    tokens_in = toint(customDimensions.input_tokens),
    tokens_out = toint(customDimensions.output_tokens),
    cost_inr = tokens_in * 0.00000175 * 85 + tokens_out * 0.000014 * 85
| summarize
    analyses = dcount(tostring(customDimensions.analysis_id)),
    total_cost_inr = sum(cost_inr)
  by user_id
| order by total_cost_inr desc
```

Used for: identifying abusive users, cost-per-active-user metric, ROI on any future subscription tier.

---

## 6. Headroom analysis — where do we hit the cap

Keeping prod running at current fixed cost (~₹6,650/mo), available variable budget = ₹12,500 - ₹6,650 = **₹5,850 for LLM spend**.

At ₹70/analysis: **~83 analyses / month** before the cap.
At 5 users that's ~4 analyses / user / week — roughly our assumed usage.

**If ops cost needs to drop to make room**:
1. Shut down dev environment outside working hours via GitHub Action cron — saves ~₹1,500/mo
2. Drop Service Bus Standard → Basic tier — saves ~₹400/mo (loses topic support, only queues — OK for Phase 2)
3. Reduce Log Analytics retention to 14 days in prod too — saves ~₹400/mo

These together free ~₹2,300 — enough for ~30 more analyses/month.
