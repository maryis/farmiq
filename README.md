# FarmIQ

Production-oriented V1 for a farmer-friendly dairy intelligence platform:

- **FeedIQ**: transparent, constraint-based ration optimization with a CVB/VEM-compatible data model.
- **HealthIQ**: per-cow baseline anomaly detection plus explainable disease-risk rules for mastitis, ketosis and lameness.
- **Ask-IQ**: Dutch/English herd chat combining structured farm tools with retrieval-grounded dairy knowledge.
- **Demo Farm**: a seeded, continuously evolving farm that makes the product useful without vendor credentials.
- **Lely integration boundary**: resumable CDC-style polling adapter designed for Lely machine/sensor data.

> V1 is decision support, not veterinary diagnosis. Demo nutrition values and health rules are illustrative and must be validated with qualified dairy nutrition/veterinary experts before production farm decisions. CVB-compatible fields are implemented without redistributing the proprietary CVB feed database.

## Run it

1. Copy environment defaults:

```bash
cp .env.example .env
```

2. Start everything:

```bash
docker compose up --build
```

3. Open:

- Web: http://localhost:3000
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/healthz

The demo farm is public by design. Non-demo farms require a JWT and farm membership.

## One-command local backend (without Docker)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
DATABASE_URL=sqlite+aiosqlite:///./farmiq.db SEED_DEMO=true uvicorn app.main:app --reload
```

The optimizer needs OR-Tools; it is installed by the API package.

## Repository layout

```text
farm-iq/
├── apps/
│   ├── api/          FastAPI, domain services, worker tasks, integration adapters
│   └── web/          Next.js 16 web application
├── infra/            Kubernetes starter manifests
├── docker-compose.yml
└── Makefile
```

## Architecture

```text
Lely / Demo / future vendors
          |
          v
  integration adapters
          |
          v
 normalized observations ---> PostgreSQL/pgvector
          |                         |
          +--> HealthIQ -----------+
          +--> FeedIQ -------------+----> FastAPI ----> Next.js
          +--> Ask-IQ tools + RAG --+

Redis <---- Celery worker/beat (NRT polling, demo ticks, risk recomputation)
```

### Near-real-time ingestion

Vendor rows are normalized into an idempotent observation contract. Each connector maintains a watermark in `sync_cursors`; repeated fetches can safely be retried. The Lely adapter intentionally keeps exact endpoint paths configurable because production partner API contracts/credentials can differ and should not be guessed.

### HealthIQ V1

HealthIQ compares a cow's recent signals to her own older baseline, then applies transparent scoring rules. Every alert carries evidence such as milk, rumination, activity or feed-intake deviation. Farmers can confirm/dismiss risks, creating labels for a future supervised model.

### FeedIQ V1

The optimizer is a linear program using dry matter, VEM, DVE, OEB, NDF, cost, inventory and per-ingredient change limits. It optimizes against configurable group requirements; the engine is deliberately isolated so validated CVB formulas/licensed feed data can replace demo parameters without changing the UI/API.

### Ask-IQ V1

Ask-IQ never receives raw SQL access. It receives controlled structured context (risks, animals, inventory, ration scenarios) and retrieved knowledge snippets. If `LLM_BASE_URL` is empty, a deterministic bilingual fallback remains fully usable for the demo. Configure any OpenAI-compatible open-weight endpoint to enable richer generation. Configure an OpenAI-compatible embedding endpoint and run `python -m app.scripts.embed_knowledge` to populate pgvector; retrieval automatically falls back to lexical matching if embeddings are unavailable.

## Auth and tenancy

`Organization -> Farm -> Group -> Animal` is the tenancy boundary. Public access is only allowed for `is_demo=true` farms. Registering creates an organization/farm and returns a JWT. API endpoints call the common access guard before exposing non-demo farm data.

## Lely integration

Public Lely documentation recommends an initial full sync plus incremental retrieval for machine/sensor data, and documents endpoints including animals, milk visits/quality, feed visits/amounts, activities and ruminations. The connector in `app/integrations/lely.py` implements token handling, configurable endpoint paths, watermarks and normalized records. Production activation requires legitimate Lely partner credentials and the exact contract supplied to the integrator.

## Production deployment

`infra/k8s/` contains a portable starter deployment. For a real environment:

- run managed PostgreSQL with the `vector` extension and backups;
- run managed Redis or a compatible broker;
- put web/API behind TLS ingress;
- store JWT/LLM/Lely credentials in the cloud's secret manager;
- set `AUTO_CREATE_DB=false` and use Alembic migrations;
- configure object storage and an embedding endpoint when document ingestion is enabled;
- run `alembic upgrade head` with `AUTO_CREATE_DB=false`;
- scrape `/metrics` and ship structured application logs/traces to your observability stack.

This repository deliberately avoids cloud-specific SDKs.

## Tests

```bash
make test-api
make test-web
```

The API test suite runs on SQLite and covers the risk engine and ration optimizer. The web build performs TypeScript/Next compilation checks.
