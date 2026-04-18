# Startup Analyzer — Finalized Implementation Plan

> **Framework**: Composite VC Framework (CVF) v1.0
> **Stack**: Next.js 15 + Python 3.12 / FastAPI
> **LLM**: `gpt-5.3-chat` on Azure AI Foundry (Azure OpenAI)
> **Search**: Native `web_search` tool via Azure OpenAI Responses API
> **Scope (v1)**: Analyzer feature only. Idea generator + history deferred to v2.

---

## 1. What changed from the original plan

| Area | Original plan | This plan |
|---|---|---|
| Backend | .NET 9 + ASP.NET Core | Python 3.12 + FastAPI |
| LLM | Claude Sonnet 4 (Anthropic) | `gpt-5.3-chat` (Azure OpenAI) |
| Web search | Claude `web_search` tool | Azure OpenAI Responses API `web_search` tool (Grounding with Bing under the hood) |
| Storage | Postgres + Redis | Postgres + Redis (local Docker for now) |
| Frontend | Next.js 15 | Next.js 15 (unchanged) |
| CQRS | MediatR | Plain service/handler classes |
| Resilience | Polly v8 | `tenacity` |
| Persistence driver | Npgsql + Dapper | `asyncpg` |
| Testing | XUnit + FluentAssertions | `pytest` + `pytest-asyncio` |
| Scope | 3 features | v1: analyzer only |

The CVF methodology itself (10 dimensions, scoring rubric, verdict thresholds, anti-hallucination layers, Mermaid report template) is unchanged.

### Weights correction
The original plan's dimension weights summed to **110%, not 100%** (a bug). We fixed it by dropping Problem Severity and Market Size from 15% → 10% each. All other weights preserved. Final weights (sum = 100):

| D1 Problem | D2 Market | D3 Solution+PMF | D4 Business | D5 Moat | D6 Timing | D7 GTM | D8 Team | D9 Traction | D10 Risk |
|---|---|---|---|---|---|---|---|---|---|
| 10% | 10% | 10% | 10% | 12% | 10% | 10% | 8% | 10% | 10% |

## 2. Model & API decisions

- **Model**: `gpt-5.3-chat` (128K input ctx, 16K output, $1.75/$14 per 1M input/output, cached $0.175/1M). Non-reasoning Instant-class SKU — sufficient for pipeline's pattern-matching + structured synthesis work.
- **Research agents** (4× parallel): use **Responses API** `client.responses.create(...)` with `tools=[{"type": "web_search"}]`. Every sourced claim flows back with citations natively.
- **Analysis, scoring, compiler agents**: use **Chat Completions** `client.chat.completions.create(...)` with `response_format={"type": "json_schema", "strict": true}`. No search needed — they consume the JSON from research agents.
- **Auth**: API key in `.env` (user choice). Entra ID upgrade is trivial later.
- **API version**: `2024-12-01-preview` to start (user-provided). If Responses API rejects on this version, bump to `2025-04-01-preview` via env var (`AZURE_OPENAI_API_VERSION`).

## 3. Anti-hallucination (unchanged methodology)

- Layer 1 — structural isolation: analysis agents write JSON only, never prose
- Layer 2 — mandatory web_search in research agents; tool enforces grounding
- Layer 3 — explicit `data_quality_warning` / `confidence` fields in every schema
- Layer 4 — score penalty rule baked into every agent prompt
- Layer 5 — source traceability: every `source_url` carried through to report
- Layer 6 — overall confidence watermark derived from agent confidence fields

## 4. Repository layout

```
startupevaluatorproject/
├── README.md
├── .env.example
├── docker-compose.yml          # postgres + redis
├── docs/IMPLEMENTATION_PLAN.md
├── backend/
│   ├── pyproject.toml
│   ├── migrations/001_initial.sql
│   ├── app/
│   │   ├── main.py             # FastAPI app
│   │   ├── config.py           # Pydantic Settings
│   │   ├── api/analysis.py     # HTTP routes + SSE
│   │   ├── core/llm.py         # AzureOpenAI wrapper (chat + responses)
│   │   ├── core/sse.py         # SSE helper
│   │   ├── core/progress.py    # PipelineProgress
│   │   ├── models/schemas.py   # Pydantic models for every agent output
│   │   ├── models/dimensions.py# CvfDimension enum + weights
│   │   ├── prompts/library.py  # All 11 prompts as constants
│   │   ├── pipeline/
│   │   │   ├── pipeline.py     # StartupAnalysisPipeline
│   │   │   ├── context.py      # dataclasses for merged context
│   │   │   └── agents/
│   │   │       ├── base.py
│   │   │       ├── orchestrator.py
│   │   │       ├── market_sizing.py
│   │   │       ├── competitive_intel.py
│   │   │       ├── news_trends.py
│   │   │       ├── regulatory.py
│   │   │       ├── problem_pmf.py
│   │   │       ├── business_model.py
│   │   │       ├── gtm_team.py
│   │   │       ├── risk_moat.py
│   │   │       ├── scoring.py
│   │   │       └── report_compiler.py
│   │   └── storage/
│   │       ├── db.py           # asyncpg pool
│   │       ├── cache.py        # redis.asyncio
│   │       └── repository.py
│   └── tests/
│       ├── conftest.py
│       ├── test_schemas.py
│       └── test_prompts.py
└── frontend/
    ├── package.json
    ├── next.config.mjs
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx            # main analyzer page
    │   └── globals.css
    ├── components/
    │   ├── AnalyzerForm.tsx
    │   ├── ProgressStream.tsx
    │   └── ReportViewer.tsx
    └── lib/api.ts
```

## 5. Pipeline flow (v1)

```
POST /api/analysis        { idea: "..." }
     → returns { analysis_id }
GET  /api/analysis/{id}/stream   (SSE)
     → events: stage updates + final { event: "done", report_url }
GET  /api/analysis/{id}/report   (markdown .md download)
```

Internal stages:

1. Orchestrator (classify + plan queries)                 → 5%
2. Research layer — 4 agents in parallel (asyncio.gather) → 45%
3. Analysis layer — batch 1 (problem_pmf + business_model) parallel → 55%
4. Analysis layer — batch 2 (gtm_team + risk_moat) parallel → 65%
5. Scoring synthesis                                      → 80%
6. Report compilation (markdown + Mermaid)                → 95%
7. Persist + done                                         → 100%

Each stage completion fires an SSE `progress` event. Agent errors downgrade to `N/A` on that dimension (partial report).

## 6. Storage

Postgres (local Docker) — two tables:

```sql
analysis_reports(id uuid pk, idea_text text, overall_score int,
                 verdict text, markdown text, confidence text,
                 created_at timestamptz)
agent_outputs(id uuid pk, analysis_id uuid fk, agent_name text,
              output_json jsonb, created_at timestamptz)
```

Redis — per-idea search-result cache (24h TTL) keyed by query hash.

## 7. v1 out-of-scope (deferred)

- Idea generator agent (Prompt 12)
- Report history UI
- User accounts + rate limiting
- Cost tracking dashboard
- Azure hosting (starting local-only)

## 8. Local run (target)

```bash
# 1. Start infra
docker-compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp ../.env.example ../.env  # fill AZURE_OPENAI_API_KEY
uvicorn app.main:app --reload

# 3. Frontend
cd ../frontend
npm install
npm run dev
# open http://localhost:3000
```

## 9. Known risks & mitigations

| Risk | Mitigation |
|---|---|
| `web_search` tool rejected on `2024-12-01-preview` | `AZURE_OPENAI_API_VERSION` is an env var; bump to `2025-04-01-preview` |
| `gpt-5.3-chat` not in web_search supported-models matrix | Smoke-test first; fallback model override via env (`AZURE_OPENAI_DEPLOYMENT_SEARCH` separate from analysis deployment) |
| Strict JSON schema rejected on some tool calls | Use Azure's JSON subset rules (no root `anyOf`, all required, ≤5 nesting) |
| Mermaid rendering in browser | `rehype-mermaid` client-side; fallback to raw code block |
| Rate / quota spikes | tenacity exponential backoff + Redis cache of search results |
