# Deploying FarmIQ to a shareable URL

FarmIQ is cloud-agnostic. The application needs four runtime roles:

1. `web` — public Next.js service.
2. `api` — private/public FastAPI service (the web server proxies `/api/*` to it).
3. `worker` + `beat` — background near-real-time ingestion/risk jobs.
4. PostgreSQL with pgvector + Redis.

## Minimum production setup

Use any container platform or Kubernetes provider that can supply PostgreSQL and Redis. Build and push:

```bash
docker build -t REGISTRY/farmiq-api:VERSION apps/api
docker build --build-arg API_INTERNAL_URL=http://farmiq-api:8000 -t REGISTRY/farmiq-web:VERSION apps/web
```

Configure these secrets at minimum:

```text
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
JWT_SECRET=<long-random-value>
AUTO_CREATE_DB=false
SEED_DEMO=true
```

Optional Ask-IQ model endpoints:

```text
LLM_BASE_URL=https://your-openai-compatible-inference/v1
LLM_API_KEY=...
LLM_MODEL=Qwen/Qwen3-8B
EMBEDDING_BASE_URL=https://your-embedding-inference/v1
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
```

Run schema migration before starting traffic:

```bash
cd apps/api
alembic upgrade head
```

If embeddings are configured, populate pgvector:

```bash
python -m app.scripts.embed_knowledge
```

## Kubernetes

`infra/k8s/farmiq.yaml` is the portable starter. Replace `YOUR_REGISTRY/*` image names, add your platform's Secret/ConfigMap, and route your HTTPS hostname to `farmiq-web` port 80. The web container internally proxies `/api/*` to `farmiq-api`, so only one public hostname is required.

## Demo URL behavior

Keep `SEED_DEMO=true` for investor/customer testing. The public Demo Farm requires no account and workers append synthetic NRT sensor events every five minutes. Real farms are not public: API access requires JWT membership.

## Before onboarding a real farm

- obtain the official Lely third-party integration contract/credentials;
- validate endpoint payload mappings in `app/integrations/lely.py` against that issued contract;
- use a secret manager rather than storing provider secrets in the DB;
- replace demo feed analyses/requirements with validated farm analyses and licensed/approved European nutrition data;
- validate HealthIQ thresholds with dairy veterinary experts and complete privacy/DPIA/security review;
- configure backups, monitoring of `/healthz` and `/metrics`, log retention, and an incident process.
