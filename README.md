# CompliMate AI Engine v2.0

## Overview

The **CompliMate AI Engine v2.0** powers **CompliMate**, an AI-driven platform for contract compliance in **Ghana's petroleum sector**. This enhanced version features advanced regulation indexing and a modern FastAPI architecture. Current active scope: **petroleum regulations only** (future expansion placeholders for mining, environmental, labor exist but are inactive).

### Core Capabilities
It automates the analysis of contracts, ensuring they meet regulations like:

- **LI 2204** (Petroleum Local Content Regulations, 2013)
- **Act 896** (Income Tax Act, 2015)
- **(Future)** Multi-sector regulation categorization (mining / environmental / labor) – placeholders only today

### Technology Stack
Built with **Python** and enhanced with:
- **LlamaIndex 0.14+** for advanced document parsing and indexing
- **ChromaDB** for persistent vector storage with fallback capabilities
- **OpenAI Advanced Models** (primary: GPT-4.1 / GPT-4o, embeddings: text-embedding-3-large, secondary refinement model)
- **FastAPI v2.0** with modular architecture
- **Hybrid retrieval** (BM25 + Vector search) for precise regulation matching
- **Two‑Phase Reasoning** (initial extraction + secondary refinement / dedup / severity scoring)
- **Smart indexing** with automatic change detection

## Overview

The **CompliMate AI Engine** powers **CompliMate**, an AI-driven platform for contract compliance in **Ghana’s petroleum sector**. It automates the analysis of contracts, ensuring they meet regulations like:

- **LI 2204** (Petroleum Local Content Regulations, 2013)
- **Act 896** (Income Tax Act, 2015)

Built with **Python**, the engine leverages:
- **LlamaIndex** for contract parsing
- **ChromaDB + GPT-4 models** for storing vector embeddings
- **(LlamaIndex, ChromaDB, BM25 + Vector search for hybrid retrieval, GPT-4)** for regulation matching
- **(GPT-4 + logic)** for violation detection 

to parse contracts and flag compliance risks efficiently.

## Key Features

### Core Analysis
- **Contract Parsing:** Advanced PDF and DOCX contract clause extraction
- **Compliance Analysis:** Hybrid search (BM25 + embeddings) + GPT for precise regulation matching
- **(Petroleum Focus)** Currently indexed: LI 2204 (additional categories reserved for future phases)
- **Performance:** Typical pilot-stage analysis completes in minutes; internal benchmarks indicate strong risk-detection potential.

### v2.0 Enhancements
- **Persistent Vector Storage:** ChromaDB with automatic persistence and fallback capabilities
- **Smart Indexing:** File hash-based change detection with selective re-indexing
- **Modern API:** FastAPI v2.0 with modular router architecture and comprehensive endpoints
- **Enhanced Metadata:** Track regulation versions, categories, and modification history
- **Robust Error Handling:** Graceful fallbacks and comprehensive logging

### Scalability & Security
- **Scalability:** Designed for high-throughput processing with horizontal worker scaling; internal benchmarks are environment-dependent.
- **Security:** Fully supports **offline operation** for sensitive data protection
- **Reliability:** Multiple storage backends with automatic failover

## Installation

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)
- Dependencies listed in `requirements.txt`
- **OCR Tools (for scanned regulation PDFs)**:
  - **Tesseract OCR** - Required for text extraction from scanned documents
  - **Poppler** - Required for PDF to image conversion
  - See `setup_ocr.md` in artifacts for installation instructions

### Current Regulation Status

**Indexed**: 16 out of 23 regulation files successfully indexed  
**Coverage**: 69.6% of available regulations  
**Failed**: 7 files pending investigation (poor scan quality/corrupted files)  

See `failed_regulations_tracking.md` for details on files requiring attention.

### Setup

**1. Clone the Repository** (private access required):
```bash
git clone https://github.com/yourusername/compli-ai-engine.git
cd compli-ai-engine
```

**2. Set Up a Virtual Environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**3. Install Dependencies:**
```bash
pip install -r requirements.txt
```

**4. Configure API Keys (if using external GPT models):**

-- Add your OpenAI API key to a `.env` file:
```env
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4.1
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
SECONDARY_REASONING_MODEL=gpt-4.1
ENABLE_SECONDARY_REASONING=True
```

- Load the key inside your code using `python-dotenv`.

## Usage

### Option 1: Command Line Interface

1. Ensure your virtual environment is activated.
2. Run the main script with a contract file:
```bash
python main.py
```
PS: A sample contract already exists in the data/contracts directory

### Option 2: API Server (v2.0)

1. Start the FastAPI server:
```bash
python main.py
```

2. Access the API:
- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/api/v1/health
- **Regulation Management:** http://localhost:8000/api/v1/regulations
# Scripts and Tests

## scripts/
Contains utility scripts for maintenance and testing:
- `rebuild_regulations_index.py`: Rebuilds the regulation vector index for Chroma or Pinecone
- `test_pdf_generator.py`: Standalone PDF report generator test

## tests/
Contains automated unit and API tests to ensure code reliability and catch regressions.

### Key API Endpoints (prefixed with /api/v1)

- `GET /api/v1/health` - System health and status
- `GET /api/v1/regulations/` - List all regulations
- `GET /api/v1/regulations/categories` - List categories
- `GET /api/v1/regulations/category/{category}` - Regulations by category
- `POST /api/v1/regulations/rebuild` - Rebuild regulation index
- `POST /api/v1/regulations/rebuild/async` - Schedule async rebuild (Celery)
- `GET /api/v1/regulations/search?query=...&category=...&limit=10` - Semantic search
- `POST /api/v1/upload` - Upload contract for analysis
- `POST /api/v1/analysis/start` - Start compliance analysis
- `GET /api/v1/analysis/{id}/status` - Check analysis status
- `GET /api/v1/analysis/{id}/results` - Get analysis results
- `GET /api/v1/tasks/{task_id}` - Background task status (Celery)
- Static mounts: `GET /ui` (demo frontend), `GET /reports/{file}` (generated reports)

### Output

Both options will:
- Parse the contract into clauses
- Analyze clauses for compliance with regulations
- Output comprehensive reports (JSON, TXT, PDF) in the `reports/` directory

## Managing Regulations

The AI engine's knowledge base can be expanded with new regulations at any time. The system is designed to automatically detect and process new or updated files.

The process is simple:

1.  **Add Regulation Files:** Place your new regulation documents (in PDF format) into the `data/regulations/` directory.

2.  **Trigger Re-indexing:** Call the asynchronous API endpoint to start the re-indexing process. This will scan the directory, find new or modified files, and add them to the vector store.

    ```bash
    curl -X POST http://localhost:8000/api/v1/regulations/rebuild/async
    ```

    You will receive a `task_id` in the response. You can use the `GET /api/v1/tasks/{task_id}` endpoint to monitor the status of the indexing task.

Once the task is complete, the new regulations will be part of the AI's knowledge base and will be used in all subsequent compliance analyses.

## License

This project is **proprietary**. All rights reserved. Contact us for licensing details.

## Contact


---

## Docker Deployment

### Build Image
```bash
docker build -t complimate-ai-engine:latest .
```

### Run Container (single service)
```bash
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY=your_key_here \
  -e ENABLE_WEBSOCKETS=True \
  -v $(pwd)/data/regulations:/app/data/regulations:ro \
  -v $(pwd)/vector_store:/app/vector_store \
  complimate-ai-engine:latest

### Run with docker-compose (API + Celery worker)

This project uses Redis (via `REDIS_URL`) as the Celery broker/result backend. RabbitMQ is not used.

1. Create a `.env` file with at least:

```
OPENAI_API_KEY=your_key_here
ENABLE_CELERY=True
REDIS_URL=redis://host.docker.internal:6379/0
# Vector DB selection:
VECTOR_DB_PROVIDER=chroma  # or "pinecone"
# For Pinecone (optional):
PINECONE_API_KEY=...
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
PINECONE_INDEX_NAME=complimate-regulations
PINECONE_NAMESPACE=default
```

2. Start services:

```powershell
docker compose up --build
```

This brings up:
- app (FastAPI at http://localhost:8000)
- worker (Celery worker; queues: rag, default)
```

### Environment Variables (Selected)
| Variable | Purpose | Default |
|----------|---------|---------|
| OPENAI_API_KEY | OpenAI authentication | (none) |
| OPENAI_MODEL | Primary reasoning model (prompt-level extraction) | gpt-4.1 |
| OPENAI_EMBEDDING_MODEL | Embedding model for vector store | text-embedding-3-large |
| SECONDARY_REASONING_MODEL | Secondary high-precision refinement model | gpt-4.1 |
| ENABLE_SECONDARY_REASONING | Enable second-pass refinement (dedupe, severity, confidence) | True |
| ENABLE_WEBSOCKETS | Enable realtime progress | True |
| REQUIRE_API_KEY | Enforce API key on protected endpoints | False |
| API_KEY | Shared secret when REQUIRE_API_KEY=True | (none) |
| MAX_WS_CONNECTIONS | Cap concurrent WebSocket connections | 100 |
| OPENAI_REQUEST_TIMEOUT | Primary LLM request timeout (seconds) | 180.0 |
| OPENAI_MAX_RETRIES | Primary LLM retry attempts | 3 |
| SECONDARY_REASONING_REQUEST_TIMEOUT | Per-call timeout for refinement (seconds) | 60 |
| SECONDARY_REASONING_DEADLINE_SECONDS | Hard deadline per refinement chunk (seconds) | 90 |
| SECONDARY_REASONING_MAX_RETRIES | Attempts per refinement chunk | 1 |
| SECONDARY_COMPLEXITY_THRESHOLD | Switch to fast model when complex | 40 |
| SECONDARY_REASONING_MODEL_FAST | Fast refinement model | gpt-4o |
| SECONDARY_BREAKER_FAIL_THRESHOLD | Refinement breaker fail threshold | 2 |
| SECONDARY_BREAKER_RESET_SECONDS | Refinement breaker cooldown (seconds) | 300 |
| REDIS_URL | Redis backing for cache (optional) | (none) |
| CACHE_TTL_SECONDS | JSON cache TTL (seconds) | 3600 |
| ENABLE_CELERY | Enable Celery integration and endpoints | False |
| CELERY_BROKER_URL | Celery broker URL (defaults to REDIS_URL) | redis://localhost:6379/0 |
| CELERY_RESULT_BACKEND | Celery result backend (defaults to REDIS_URL) | redis://localhost:6379/0 |
| VECTOR_DB_PROVIDER | Vector DB provider: chroma or pinecone | chroma |
| PINECONE_API_KEY | Pinecone API key (if using pinecone) | (none) |
| PINECONE_CLOUD | Pinecone serverless cloud | aws |
| PINECONE_REGION | Pinecone serverless region | us-east-1 |
| PINECONE_INDEX_NAME | Pinecone index name | complimate-regulations |
| PINECONE_NAMESPACE | Pinecone namespace | default |
| HYBRID_SEARCH_TOP_K | Hybrid retrieval top-k | 5 |
| REPORT_ENHANCED_MODE | Enable enhanced report layout (Phase 1) | True |
| INCLUDE_EXEC_SUMMARY | Include Executive Summary section | True |
| INCLUDE_MRIA | Include Matters Requiring Immediate Attention | True |

### Health Check
```bash
curl -s http://localhost:8000/api/v1/health | jq
```

---

## Continuous Integration (GitHub Actions)

Two workflows:

1. `ci.yml` (on PR & main):
	- Install deps, lint (syntax compile), run tests, build Docker image.
2. `release.yml` (on tag `v*`):
	- Tests + optional `pip-audit` + build & push image to GHCR.

### Tagging a Release
```bash
git tag v2.0.2
git push origin v2.0.2
```
This pushes container: `ghcr.io/<owner>/complimate-ai-engine:v2.0.2`.

---

## WebSockets (Realtime Progress)

Endpoint: `ws://localhost:8000/ws/analysis/{analysis_id}` (enabled when `ENABLE_WEBSOCKETS=True`)

Example:
```js
const ws = new WebSocket('ws://localhost:8000/ws/analysis/demo');
ws.onmessage = e => console.log(JSON.parse(e.data));
```
See `docs/WEBSOCKETS.md` for full schema.

---

📧 **Email:** coming soon

For more about **CompliMate**, see our landing page - complighana.com
> **Powering Compliance with AI for Ghana’s Petroleum Sector** 

---

## Docs

- Investor & Buyer Brief: docs/complimate-investor-and-buyer-brief.md
- Developer Manual (end-to-end): docs/developer/README.md

---

## Two‑Phase Reasoning Pipeline (High Fidelity Mode)

1. Extraction (Primary Model: `OPENAI_MODEL`)
  - Parallel clause × regulation pairing prompts
  - Produces candidate violation objects with raw issue descriptions.
2. Refinement (Secondary Model: `SECONDARY_REASONING_MODEL`)
  - Activated when `ENABLE_SECONDARY_REASONING=True`.
  - Deduplicates semantically similar findings.
  - Adds: `severity` (Low|Medium|High|Critical), `confidence` (0–1), `rationale` sentence.
  - Removes low-evidence / unsupported candidates.

Refinement applies conservative deduplication:
- Only merges items that share the same Category and the same Regulation Ref, and that describe essentially the same Issue (normalized match; optional similarity threshold via USE_EMBEDDING_SIMILARITY/DEDUPE_SIM_THRESHOLD).
- Distinct obligations under the same category but different regulation references remain separate.
- Guardrails prevent over-pruning within a category+regulation cluster.

Refinement stats are embedded in each report under the `refinement` block.

If the secondary pass fails (timeout / API error) the original extraction set is preserved (fail‑open for safety).

Report rendering:
- Grouped view shows Category headings and a single per-item “Regulation Ref” line directly beneath the Issue. We intentionally removed the group-level “Regulation:” header to avoid duplication.

### Choosing Models for Maximum Reasoning Fidelity

Recommended production trio:
| Role | Env Var | Suggested Model |
|------|---------|-----------------|
| Primary extraction | OPENAI_MODEL | gpt-4.1 (or gpt-4o if cost sensitive) |
| Embeddings | OPENAI_EMBEDDING_MODEL | text-embedding-3-large |
| Secondary refinement | SECONDARY_REASONING_MODEL | gpt-4.1 |

You can downshift to `gpt-4o-mini` for primary if throughput > cost ratio is critical; keep refinement on `gpt-4.1` to retain precision.

### Re-indexing After Embedding Model Changes

If you change `OPENAI_EMBEDDING_MODEL`, purge the existing vector store to avoid mixed dimensionality:

```bash
rm -rf vector_store/*  # or corresponding persistent volume contents
python scripts/rebuild_regulations.py  # (future utility) or trigger rebuild endpoint
```

### Observability
- Report includes `models` block enumerating active model IDs and whether secondary was enabled.
- Future: expose via `/health` or `/meta` endpoint.

---

## Performance and Security Notes

- Prompt scrubbing removes emails, phone numbers, and account/ID-like tokens before sending prompts to LLMs, reducing PII exposure.
- Multi-layer caching:
  - Retrieval caching for clause→regulation lookups
  - Primary prompt caching to skip repeated LLM calls
  - Refinement per-chunk caching to avoid redundant second-pass calls
- Refinement is time-bounded with a circuit breaker; failures fail-open so extraction results are preserved.

See `docs/PERFORMANCE.md` for all knobs and guidance.

---
