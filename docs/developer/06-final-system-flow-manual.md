# 06 — Final System Flow Manual (End-to-End)

This is the consolidated end-to-end reference that ties all foundational documents together.

Related docs:
- Scope/personas: `01-project-scope-and-user-types.md`
- Architecture: `02-architecture-and-quality-attributes.md`
- API/contracts: `03-api-reference-and-contracts.md`
- Diagrams: `04-system-diagrams.md`
- Deployment/env: `05-deployment-and-environment-guide.md`

---

## End-to-End Lifecycle Overview

## Phase 1 — Access and Identity

1. User/service authenticates (JWT or API key where enforced).
2. Role context determines admin/user capabilities for protected endpoints.
3. Audit events are persisted for key auth actions.

## Phase 2 — Input Ingestion

1. Contract uploaded via `/api/v1/upload`.
2. File is validated (type/size), persisted to disk, metadata stored in DB.
3. `file_id` becomes primary input token for analysis start.

## Phase 3 — Analysis Orchestration

1. Analysis requested via `/api/v1/analysis/start`.
2. Analysis row created in DB (`started` → `running`).
3. Background execution dispatched:
   - asyncio task by default,
   - Celery worker when enabled.

## Phase 4 — AI Pipeline Execution

1. Parse contract into nodes.
2. Retrieve relevant regulation chunks (hybrid retrieval).
3. Generate LLM prompts per contract/regulation pair.
4. Execute bounded concurrent model calls.
5. Aggregate violation candidates.
6. Optional secondary refinement phase with timeout/retry/deadline controls.
7. Circuit breakers protect against unstable upstream failure patterns.

## Phase 5 — Output and Delivery

1. Generate result summary and JSON/TXT/PDF reports.
2. Persist analysis completion state and report paths.
3. Client retrieves status/results via REST.
4. Optional realtime progress events delivered over WebSocket.

---

## User-Type Flows

## Anonymous/Public Client Flow

- Discover service (`/`, `/docs`, `/api/v1/health`).
- May use upload/analyze/regulations in current implementation where route-level auth is not enforced.

## Authenticated User Flow

- Login → token issuance.
- Upload contract → start analysis → poll status/results.
- Manage own profile, password, and API keys.

## Admin Flow

- All user flow capabilities.
- User listing and audit log retrieval.
- Operational oversight for compliance usage and access events.

## Service Client (API Key) Flow

- Non-interactive integration calls with API key bearer token.
- Poll-based result retrieval and optional WebSocket consumption.

## DevOps/Operator Flow

- Configure env vars and deployment mode.
- Enable/disable Celery/WebSockets.
- Monitor health and background worker state.

---

## System Guarantees and Operational Boundaries

Designed to provide:

- practical reliability controls (timeouts, retries, breakers),
- scalable async processing path (queue-backed optional),
- domain-focused retrieval/reasoning quality path,
- deployment flexibility (local, Docker, compose, offline-capable posture).

Current boundaries:

- no native webhook sender contract yet,
- some enterprise hardening tracks remain roadmap-managed,
- optimization remains profiling-led (Python-first architecture retained).

---

## Required Artifacts for Decision-Grade Rollout

Before broad rollout messaging, maintain a metrics evidence package:

- p50/p95 latency,
- cache hit rate,
- failure/retry rates by stage,
- precision/false-positive pilot review,
- cost per contract.

This aligns technical quality with buyer/investor confidence while preserving a pragmatic engineering narrative.

