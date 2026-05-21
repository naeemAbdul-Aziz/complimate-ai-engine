# 02 — Architecture and Quality Attributes

## Architecture Summary

CompliMate is a Python/FastAPI system with modular layers:

- **API layer** (`api/endpoints/*`): HTTP + WebSocket surfaces.
- **Service layer** (`api/services/*`): analysis, file, auth business logic.
- **Engine layer** (`engine/*`): parsing, retrieval, violation detection, secondary refinement.
- **Persistence layer**:
  - SQLModel/SQLAlchemy async DB (analyses, uploads, auth entities).
  - Vector store (Chroma by default, optional Pinecone).
  - Filesystem for uploads/reports.
- **Async execution**:
  - in-process asyncio tasks (default),
  - optional Celery worker + Redis broker/result backend.

---

## Python-Only Optimization Posture

Current recommended posture:

- Keep Python/FastAPI architecture as the production baseline.
- Optimize hotspots **after profiling**, not preemptively.
- Prioritize measurable improvements:
  - p50/p95 latency,
  - cache hit rate,
  - cost per contract,
  - stage-level retry/failure rates,
  - pilot precision/false-positive quality.

Not recommended until justified by measured bottlenecks:

- Runtime rewrite (e.g., Rust),
- premature microservice split,
- Kubernetes-first replatforming without customer requirement.

---

## Scalability Design

### Horizontal and Functional Scaling

- API process can scale horizontally behind a load balancer.
- Background analysis can be offloaded to Celery workers.
- Regulation indexing heavy jobs route to dedicated Celery queue (`rag`).
- Vector DB choice is configurable (Chroma/Pinecone).

### Concurrency and Throughput Controls

- OpenAI concurrency limit (`OPENAI_CONCURRENCY_LIMIT`).
- Request timeout/retry controls (`OPENAI_REQUEST_TIMEOUT`, `OPENAI_MAX_RETRIES`).
- Secondary reasoning deadline/timeouts and retry cap.
- Circuit breakers for primary and secondary stages.

### Real-Time Scaling Considerations

- WebSocket connection cap (`MAX_WS_CONNECTIONS`).
- Throttled progress broadcast to reduce event floods.
- Current docs acknowledge backpressure hardening as a next-stage area.

---

## Security Design

### Identity and Access

- JWT access + refresh token model.
- API key model for service authentication.
- Role-based authorization helpers (`user`, `analyst`, `admin`).
- Account lockout controls after failed attempts.

### Data Protection and Runtime Hardening

- Environment-based secret management.
- Non-root runtime user in Docker image.
- Security headers middleware (XFO, CSP, etc.).
- Optional offline/on-prem deployment posture for sensitive environments.

### Security Hardening Roadmap Focus

- Broader endpoint-level auth enforcement consistency.
- stronger API auth defaults by deployment profile.
- expanded audit trail policy and retention controls.
- RBAC + SSO integration progression.

---

## Consistency and Reliability Design

- Persistent DB-backed analysis and upload metadata.
- Fail-open/controlled-degradation behavior in selected AI pipeline steps.
- Circuit-breaker isolation for unstable upstream LLM behavior.
- Tolerant structured output processing and bounded retries.
- Shared service abstractions for repeatable endpoint behavior.

---

## Maintainability Design

- Modular separation: endpoints/services/engine/models/config/tasks.
- Strong schema usage (Pydantic/SQLModel) for contract clarity.
- Centralized settings in `config/settings.py`.
- Clear deployment artifacts: Dockerfile and docker-compose.
- Existing docs for performance tuning, API references, websocket behavior.

---

## Current Maturity (Honest Positioning)

Production-minded and credible for pilot/early scale:

- strong retrieval/reasoning architecture,
- bounded latency/retry controls,
- caching and breaker logic,
- containerized deployment flexibility.

Still evolving:

- full enterprise hardening depth (SSO/RBAC/audit lifecycle),
- formalized evaluation harness breadth,
- complete realtime backpressure strategy.

