# 05 — Deployment and Environment Guide

## Deployment Modes

## 1) Local Single-Process API

- Runs FastAPI service.
- Async background analysis uses in-process asyncio tasks.
- Suitable for local dev and small pilot loads.

Command:

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## 2) Docker Single-Service

- Uses production Dockerfile.
- Non-root runtime user.

```bash
docker build -t complimate-ai-engine:latest /home/runner/work/complimate-ai-engine/complimate-ai-engine
docker run --rm -p 8000:8000 --env-file .env complimate-ai-engine:latest
```

## 3) Docker Compose with Redis + Celery Worker

- `app` + `worker` + `redis`.
- Async analysis/indexing can run through Celery.

```bash
docker compose -f /home/runner/work/complimate-ai-engine/complimate-ai-engine/docker-compose.yml up --build
```

---

## Required and Critical Environment Variables

## Core Runtime

- `OPENAI_API_KEY` (required for active LLM operations)
- `DATABASE_URL` (required by `api/db.py`; app fails startup without it)

Example:

```env
DATABASE_URL=sqlite+aiosqlite:///./sql_app.db
OPENAI_API_KEY=...
```

## API

- `API_HOST` (default `127.0.0.1`)
- `API_PORT` (default `8000`)
- `API_RELOAD`
- `API_LOG_LEVEL`

## Retrieval and Models

- `OPENAI_MODEL`
- `OPENAI_EMBEDDING_MODEL`
- `SECONDARY_REASONING_MODEL`
- `ENABLE_SECONDARY_REASONING`
- `HYBRID_SEARCH_TOP_K`

## Timeout / Retry / Reliability

- `OPENAI_REQUEST_TIMEOUT`
- `OPENAI_MAX_RETRIES`
- `SECONDARY_REASONING_REQUEST_TIMEOUT`
- `SECONDARY_REASONING_DEADLINE_SECONDS`
- `SECONDARY_REASONING_MAX_RETRIES`
- `CIRCUIT_BREAKER_FAIL_THRESHOLD`
- `CIRCUIT_BREAKER_RESET_SECONDS`
- `SECONDARY_BREAKER_FAIL_THRESHOLD`
- `SECONDARY_BREAKER_RESET_SECONDS`

## Async and Queueing

- `ENABLE_CELERY`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

## Storage and Paths

- `VECTOR_DB_PROVIDER` (`chroma` or `pinecone`)
- `VECTOR_STORE_DIR`
- `REGULATIONS_DIR`
- `UPLOADS_DIR`
- `REPORTS_DIR`

Optional Pinecone variables:
- `PINECONE_API_KEY`
- `PINECONE_INDEX_NAME`
- `PINECONE_NAMESPACE`
- `PINECONE_CLOUD`
- `PINECONE_REGION`

## Security and Access

- `CORS_ORIGINS`
- `REQUIRE_API_KEY`
- `API_KEY`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `MAX_LOGIN_ATTEMPTS`
- `LOCKOUT_DURATION_MINUTES`

## WebSocket

- `ENABLE_WEBSOCKETS`
- `MAX_WS_CONNECTIONS`
- `WS_HEARTBEAT_SECONDS`

---

## Data Persistence Surfaces

- SQL DB (users, auth artifacts, uploaded file records, analyses)
- `uploads/` directory
- `reports/` directory
- vector store directory (`vector_store/`) or Pinecone index

For container deployment, mount persistent volumes for all required state directories.

---

## Operational Health and Verification

## Startup checks

- `GET /api/v1/health` should return healthy payload.
- Verify `openai_configured=true` when LLM features required.
- Confirm regulation index loaded (`regulation_loaded` field).

## Functional checks

1. Upload contract.
2. Start analysis.
3. Poll status until complete.
4. Fetch results/report paths.
5. If Celery enabled, validate `/api/v1/tasks/{task_id}`.
6. If WebSockets enabled, validate connection to analysis stream.

---

## Deployment Security Checklist

- Set strong non-default `JWT_SECRET_KEY` in production.
- Restrict `CORS_ORIGINS` (avoid wildcard in production internet contexts).
- Protect OpenAI and database credentials in secret manager/secure env.
- Disable docs endpoints in strict production profiles if required.
- Enforce auth controls and API key policy appropriate to threat model.
- Use TLS termination at ingress/load-balancer layer.

