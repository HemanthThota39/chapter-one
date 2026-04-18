# Chapter One

> **It all starts with Chapter One.**
>
> A collaborative idea-evaluation platform where friends generate, analyse, debate, and share startup ideas using a grounded-research AI agent.

Each idea becomes a **report** built on the Composite VC Framework (10 dimensions, web-search-grounded via Azure AI Foundry), shared to a global feed, and open to factual debate that can patch the report section-by-section.

**Status**: Phase 2 in active development ([roadmap](docs/phase2/09-roadmap.md)).

---

## Architecture at a glance

- **Frontend**: Next.js 15 App Router, Tailwind, SSE for real-time progress — hosted on **Azure Static Web Apps**
- **Backend**: Python 3.12 + FastAPI, multi-query research engine — hosted on **Azure Container Apps**
- **Workers**: analysis pipeline, PDF renderer, daily cron — **Container Apps Jobs**
- **Data**: **Postgres Flexible Server** (all relational), **Blob Storage** (PDFs, avatars, raw agent outputs), **Service Bus** (job queue)
- **LLM**: `gpt-5.3-chat` on **Azure AI Foundry** with native `web_search` tool
- **Auth**: **Entra External ID** with Google OAuth
- **Secrets**: **Azure Key Vault** + Managed Identity
- **Observability**: **Application Insights** + Log Analytics

Full architecture: [`docs/phase2/02-architecture.md`](docs/phase2/02-architecture.md).

## Documentation

The complete specification is in [`docs/phase2/`](docs/phase2/):

1. [`00-overview.md`](docs/phase2/00-overview.md) — vision, personas, goals
2. [`01-requirements.md`](docs/phase2/01-requirements.md) — FRs + NFRs
3. [`02-architecture.md`](docs/phase2/02-architecture.md) — system design
4. [`03-data-model.md`](docs/phase2/03-data-model.md) — Postgres schema
5. [`04-apis.md`](docs/phase2/04-apis.md) — API contracts
6. [`05-security.md`](docs/phase2/05-security.md) — auth & threat model
7. [`06-infrastructure.md`](docs/phase2/06-infrastructure.md) — Azure resources
8. [`07-operations.md`](docs/phase2/07-operations.md) — CI/CD & observability
9. [`08-cost-model.md`](docs/phase2/08-cost-model.md) — costs
10. [`09-roadmap.md`](docs/phase2/09-roadmap.md) — milestones
11. [`10-decisions.md`](docs/phase2/10-decisions.md) — 26 ADRs

## Local development

**Prereqs:** Python 3.12+, Node 20+, Docker (optional — Postgres + Redis run locally via docker-compose or natively via Homebrew).

```bash
# 1. Clone + env
git clone https://github.com/<owner>/chapter-one.git
cd chapter-one
cp .env.example .env
# fill AZURE_OPENAI_API_KEY in .env

# 2. Infra (optional for full stack; skip for in-memory mode)
docker compose up -d   # or: brew install postgresql@16 redis && brew services start ...

# 3. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000

# 4. Frontend
cd ../frontend
npm install
npm run dev
# open http://localhost:3000
```

Run tests: `cd backend && pytest` · `cd frontend && npm test`

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). TL;DR: open an issue first for anything non-trivial, sign your commits with `-s`, CI must be green.

## License

MIT — see [`LICENSE`](LICENSE).
