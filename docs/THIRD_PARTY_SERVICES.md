# CompliMate AI Engine — Third-Party Services Setup Guide

This document explains how to create accounts, configure credentials, and connect
every external service the CompliMate AI Engine depends on.

---

## Services Overview

| Service | Purpose | Required |
|---|---|---|
| **OpenAI** | LLM analysis + text embeddings | ✅ Required |
| **Pinecone** | Cloud vector database for regulation search | ✅ Required in production |
| **PostgreSQL** | Persistent relational DB for analyses, users, regulation metadata | ✅ Required in production |
| **Redis** | Caching (LLM responses, retrieval results) + Celery broker | Optional |
| **AWS S3** | Cloud storage for regulation PDFs | Phase 2 (Optional now) |

---

## 1. OpenAI

### What it's used for
- **GPT-4.1** (`OPENAI_MODEL`): Primary LLM for contract clause analysis and violation detection
- **text-embedding-3-large** (`OPENAI_EMBEDDING_MODEL`): Converts regulation text chunks into 3072-dimension vectors for Pinecone

### Setup Steps

1. Go to [platform.openai.com](https://platform.openai.com) and create an account.
2. Navigate to **API Keys** → **Create new secret key**.
3. Copy the key (it starts with `sk-proj-...`).
4. Add to `.env`:
   ```env
   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-4.1
   OPENAI_EMBEDDING_MODEL=text-embedding-3-large
   ```

### Costs & Limits
| Model | Approx. cost per analysis |
|---|---|
| GPT-4.1 (10 concurrent calls, ~25 contract nodes) | ~$0.30–0.80 per contract |
| text-embedding-3-large (23 regulation PDFs, first index) | ~$0.05 one-time |
| text-embedding-3-large (per contract analysis) | ~$0.001 |

> [!TIP]
> Set `PERFORMANCE_PRESET=fast` to reduce costs during development. This uses fewer tokens per call.

### Rate Limiting
The engine has a built-in circuit breaker. If you see 429 errors, reduce `OPENAI_MAX_REQUESTS_PER_MINUTE` in `.env`.

---

## 2. Pinecone

### What it's used for
Stores dense vector embeddings of regulation text chunks. During analysis, the engine uses Pinecone to find the most semantically relevant regulation sections for each contract clause.

### Setup Steps

1. Go to [app.pinecone.io](https://app.pinecone.io) and create a free account.
2. Click **Create Index**:
   - **Index name:** `complimate-regulations`
   - **Dimensions:** `3072` (required for `text-embedding-3-large`)
   - **Metric:** `cosine`
   - **Cloud:** `AWS`
   - **Region:** `us-east-1`
3. Click **API Keys** in the left sidebar → copy your API key.
4. Add to `.env`:
   ```env
   VECTOR_DB_PROVIDER=pinecone
   PINECONE_API_KEY=pcsk_...
   PINECONE_CLOUD=aws
   PINECONE_REGION=us-east-1
   PINECONE_INDEX_NAME=complimate-regulations
   PINECONE_NAMESPACE=default
   ```

> [!IMPORTANT]
> The index **must be created with 3072 dimensions** to match `text-embedding-3-large`. Using a different embedding model will require deleting and recreating the index.

### First-Time Regulation Ingestion
After setting up Pinecone, populate the index by running the ingestion script once:
```bash
# Activate venv first
python scripts/ingest_regulations.py

# To force re-index all files (e.g. after model change):
python scripts/ingest_regulations.py --force
```

This will OCR + embed all 23 PDFs and push them to Pinecone. Expect ~15–20 minutes on first run. The API server does **not** need to be running for this.

### Free Tier Limits
Pinecone's free Starter plan supports up to **100,000 vectors**. The current 23 regulation PDFs generate approximately 250–300 chunks total, well within limits.

---

## 3. PostgreSQL (Production)

### What it's used for
Stores all relational data: uploaded file metadata, analysis job state and results, user accounts, API keys, JWT refresh tokens, audit logs, and regulation document lifecycle state (`regulation_documents` table).

### Setup Options

#### Option A: Managed Cloud (Recommended)
- **Supabase** (free tier available): [supabase.com](https://supabase.com)
- **Neon** (serverless Postgres, free tier): [neon.tech](https://neon.tech)
- **Railway**: [railway.app](https://railway.app)
- **AWS RDS** / **GCP Cloud SQL**: For enterprise deployments

#### Option B: Self-Hosted with Docker
```bash
docker run -d \
  --name complimate-postgres \
  -e POSTGRES_USER=complimate \
  -e POSTGRES_PASSWORD=<strong-password> \
  -e POSTGRES_DB=complimate_db \
  -p 5432:5432 \
  postgres:16
```

### Configuration
Add to `.env`:
```env
DATABASE_URL=postgresql+asyncpg://complimate:<password>@localhost:5432/complimate_db
```

### Running Migrations
After setting `DATABASE_URL`, run the database migrations:
```bash
# The app auto-creates tables on startup via SQLModel create_all
# For production, generate Alembic migrations instead:
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

> [!NOTE]
> For **local development**, SQLite is the default and requires no setup:
> ```env
> DATABASE_URL=sqlite+aiosqlite:///./sql_app.db
> ```

---

## 4. Redis (Optional)

### What it's used for
- **LLM response caching**: Avoids re-calling OpenAI for identical clause+regulation prompts
- **Retrieval caching**: Caches BM25/vector retrieval results per clause
- **Celery broker**: If `ENABLE_CELERY=True`, Redis is used to queue background ingestion jobs

### When to enable
Redis is optional. The system gracefully falls back to in-memory caching when Redis is unavailable. Enable Redis in production to:
- Reduce OpenAI costs by ~20–40% on repeated analyses
- Support Celery-based background jobs

### Setup Options

#### Local (Development)
```bash
# Windows via Scoop
scoop install redis

# Or via Docker
docker run -d --name complimate-redis -p 6379:6379 redis:7

# Start Redis
redis-server
```

#### Cloud (Production)
- **Redis Cloud** free tier: [redis.com/try-free](https://redis.com/try-free)
- **Upstash** (serverless Redis): [upstash.com](https://upstash.com)
- **AWS ElastiCache**: For AWS deployments

### Configuration
```env
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=3600
ENABLE_CELERY=False   # Set to True to use Celery for background ingestion jobs
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

---

## 5. AWS S3 (Phase 2 — Not Required Now)

### What it's used for (Phase 2)
Stores regulation PDFs in the cloud so the API server doesn't need a local filesystem mount. Required for horizontal scaling (multiple API server instances) and containerized deployments.

### Current Status
`CLOUD_STORAGE_PROVIDER=local` — PDFs are stored in `data/regulations/` on the server. This works for a single-instance deployment.

### Setup Steps (When Ready)
1. Create an AWS account at [aws.amazon.com](https://aws.amazon.com).
2. Create an S3 bucket named `complimate-regulations` in your preferred region.
3. Create an IAM user with `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` permissions on that bucket.
4. Generate Access Keys for the IAM user.
5. Add to `.env`:
   ```env
   CLOUD_STORAGE_PROVIDER=s3
   AWS_S3_BUCKET_NAME=complimate-regulations
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=us-east-1
   ```

---

## 6. V3 Admin API Key

### What it's used for
Protects the admin regulation management endpoints (`POST /upload`, `GET /doc/{id}`, `DELETE /doc/{id}`). These endpoints allow adding and removing regulation PDFs from the live system.

### Generate a Secure Key
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Configuration
```env
ADMIN_API_KEY=<your-generated-hex-string>
```

### Usage
All admin endpoints require the `X-Admin-Key` header:
```bash
# Upload a new regulation
curl -X POST http://localhost:8000/api/v1/regulations/upload \
  -H "X-Admin-Key: your-admin-key" \
  -F "file=@new_regulation.pdf" \
  -F "title=New Regulation Title" \
  -F "category=petroleum"

# Check indexing status
curl http://localhost:8000/api/v1/regulations/doc/42 \
  -H "X-Admin-Key: your-admin-key"

# Retire a regulation
curl -X DELETE http://localhost:8000/api/v1/regulations/doc/42 \
  -H "X-Admin-Key: your-admin-key"
```

> [!CAUTION]
> Never expose `ADMIN_API_KEY` in client-side code or public repositories. Treat it like a database password.

---

## Quick Start Checklist

```bash
# 1. Copy and configure .env
cp .env.example .env   # edit with your real keys

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run database initialization
python -c "from api.db import init_db; import asyncio; asyncio.run(init_db())"

# 4. Index all regulations into Pinecone (one-time setup)
python scripts/ingest_regulations.py

# 5. Start the API server
python main.py
# or: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Verify everything is working
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/regulations/status
```

---

## Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `OPENAI_MODEL` | ✅ | LLM model name (default: `gpt-4.1`) |
| `OPENAI_EMBEDDING_MODEL` | ✅ | Embedding model (default: `text-embedding-3-large`) |
| `PINECONE_API_KEY` | ✅ Production | Pinecone API key |
| `PINECONE_INDEX_NAME` | ✅ Production | Pinecone index name (default: `complimate-regulations`) |
| `PINECONE_CLOUD` | ✅ Production | `aws` or `gcp` |
| `PINECONE_REGION` | ✅ Production | e.g. `us-east-1` |
| `PINECONE_NAMESPACE` | ✅ Production | Namespace prefix (default: `default`) |
| `VECTOR_DB_PROVIDER` | ✅ | `pinecone` (production) or `chroma` (dev) |
| `DATABASE_URL` | ✅ | SQLAlchemy async DB URI |
| `JWT_SECRET_KEY` | ✅ | Pre-generated random secret (min 48 chars) |
| `ADMIN_API_KEY` | ✅ Admin | Protects regulation management endpoints |
| `REDIS_URL` | Optional | Redis connection URI |
| `ENABLE_CELERY` | Optional | `True` to enable background job queue |
| `CLOUD_STORAGE_PROVIDER` | Optional | `local` or `s3` (default: `local`) |
| `MAX_REGULATION_FILE_SIZE_MB` | Optional | Upload size limit (default: `50`) |

---
*Document Version: 3.0 | Last Updated: 2026-05-22*
