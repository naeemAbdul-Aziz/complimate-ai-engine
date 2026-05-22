# 01 — Project Scope and User Types

## Purpose

Define exactly what this system is, what it is not, who uses it, and what each user can/cannot do.

---

## In Scope (Current Product Scope)

- AI-assisted compliance analysis for **Ghana petroleum contracts**.
- FastAPI backend for upload, analysis, regulation retrieval, auth, and task status.
- Hybrid retrieval (BM25 + embeddings) and two-stage reasoning pipeline.
- Async background execution (asyncio and optional Celery).
- Optional WebSocket progress stream.
- JSON/TXT/PDF report generation.
- Dockerized deployment and optional Redis/Celery topology.
- Optional offline/on-prem deployment posture.

## Out of Scope (Current State)

- Generalized multi-industry compliance platform (beyond active petroleum wedge).
- Guaranteed legal advice or fully autonomous legal decisioning.
- Hard enterprise guarantees not yet implemented end-to-end (e.g., complete SSO/RBAC/audit hardening program across all surfaces).
- Native outbound webhook delivery pipeline (no first-class webhook publisher currently implemented).
- Kubernetes-specific runtime assumptions.
- Language/runtime rewrite away from Python without measured profiling evidence.

---

## System Personas (User Types)

## 1) Anonymous/Public API Consumer

Typical actor:
- Integrator or client app before authentication.

Can:
- Access root metadata (`GET /`), docs (`/docs`, `/redoc`), and health (`GET /api/v1/health`).
- Register account (`POST /api/v1/auth/register`) and login (`POST /api/v1/auth/login`).
- Call currently unauthenticated operational endpoints where auth dependency is not enforced (upload/analysis/regulations in current implementation).

Cannot:
- Access role-protected admin endpoints (`/api/v1/auth/users`, `/api/v1/auth/audit-logs`) without valid admin auth.

---

## 2) Authenticated User (`role=user`)

Can:
- Read own profile (`GET /api/v1/auth/me`) and update profile (`PUT /api/v1/auth/me`).
- Change password (`POST /api/v1/auth/change-password`).
- Manage own API keys (`POST/GET/DELETE /api/v1/auth/api-keys...`).
- Access compliance workflows currently not role-guarded (upload, analysis, regulations), subject to deployment policy.

Cannot:
- Access admin-only user listing and global audit logs.
- Assign privileged roles during self-registration (non-admin role override is enforced back to `user`).

---

## 3) Analyst (`role=analyst`)

Can:
- All `user` capabilities.
- Intended privileged read/analysis workflows where deployments choose to enforce analyst role gates.

Cannot:
- Access admin-only endpoints unless promoted to `admin`.

---

## 4) Admin (`role=admin`)

Can:
- All user/analyst capabilities.
- List users (`GET /api/v1/auth/users`).
- Query audit logs (`GET /api/v1/auth/audit-logs`).
- Register users with elevated roles.

Cannot:
- Bypass runtime requirements (e.g., OpenAI key for active LLM workflows) at application level.

---

## 5) Service Client (API Key-based)

Can:
- Authenticate via bearer API key path (auth dependency supports JWT or API key).
- Access endpoints that enforce `get_current_user` and accept bearer credentials.
- Run automated CI/partner integration flows where API keys are enabled.

Cannot:
- Exceed API-key lifecycle/active constraints (`is_active`, expiration).
- Gain role permissions higher than the owning user.

---

## 6) Platform/DevOps Operator

Can:
- Configure environment, deployment topology, worker model, storage, and secrets.
- Enable/disable Celery and WebSockets.
- Configure database backend, rate limits, timeouts, and breaker thresholds.

Cannot:
- Change business logic behavior without code/config release process.

---

## Permission and Access Notes

- Auth dependencies exist for current user and role checks (`require_active_user`, `require_admin`, etc.).
- Some analysis/regulation endpoints currently operate without explicit auth dependency.
- WebSocket endpoint supports optional API key gate when `REQUIRE_API_KEY=True`.
- Security posture should be treated as **designed for enterprise deployment requirements**, with staged hardening in roadmap areas.

