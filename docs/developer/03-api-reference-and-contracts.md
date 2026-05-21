# 03 — API Reference and Contracts (Exhaustive)

## Base and Discovery

- Base URL: `http://<host>:8000`
- Swagger: `/docs`
- ReDoc: `/redoc`

## Global Prefixes

- REST API prefix: `/api/v1`
- Auth prefix: `/api/v1/auth`
- Analysis prefix: `/api/v1/analysis`
- Regulation prefix: `/api/v1/regulations`
- Task prefix: `/api/v1/tasks`
- WebSocket router mounted at `/ws` with route `/ws/analysis/{analysis_id}` resulting in effective path:  
  `ws://<host>:8000/ws/ws/analysis/{analysis_id}` (current implementation path composition).

---

## Authentication Contracts

Supported auth mechanisms:

- `Authorization: Bearer <jwt_access_token>`
- `Authorization: Bearer <api_key>`

Role model:

- `user`, `analyst`, `admin`

Admin-only:

- `GET /api/v1/auth/users`
- `GET /api/v1/auth/audit-logs`

---

## Root and Static

### `GET /`
Returns service metadata and endpoint hints.

### `GET /ui` (if frontend exists)
Static demo UI.

### `GET /reports/{path}`
Generated report file static serving.

### `GET /uploads/{path}`
Uploaded file static serving.

---

## Health

### `GET /api/v1/health`
Response model: `HealthResponse`

Key fields:
- `status`
- `timestamp`
- `regulation_loaded`
- `openai_configured`
- `version`
- `cooldown_active`
- `cooldown_remaining_seconds`
- `regulations_indexed`
- `last_rebuild_status`
- `consecutive_rate_limits`

---

## Upload

### `POST /api/v1/upload`
Content-Type: `multipart/form-data`

Form fields:
- `file` (required)

Response model: `ContractUploadResponse`

Success fields:
- `message`
- `file_name`
- `file_id`
- `file_path`
- `file_size`
- `uploaded_at`

Errors:
- `400` invalid/unsupported upload inputs.

---

## Analysis

### `POST /api/v1/analysis/start`
Body contract (JSON):

```json
{
  "file_id": "uuid-string"
}
```

Compatibility note:
- legacy `contract_id` accepted in payload parsing but intentionally rejected with `400`.

Response model: `AnalysisStartResponse`

Fields:
- `message`
- `analysis_id`
- `status` (`started`)
- `estimated_duration`
- `started_at`

Errors:
- `400` missing/invalid start payload
- `404` file id not found/missing file

### `GET /api/v1/analysis/{analysis_id}/status`
Response model: `AnalysisStatusResponse`

Errors:
- `400` invalid UUID format
- `404` analysis not found

### `GET /api/v1/analysis/{analysis_id}/results`
Response model: `AnalysisStatusResponse` (completed/failed detail path)

Errors:
- `400` invalid UUID format
- `404` analysis not found
- `409` analysis exists but not yet completed

### `GET /api/v1/analysis/`
Response model: `List[AnalysisStatusResponse]` (recent-first list)

---

## Regulations

### `GET /api/v1/regulations/`
Response model: `RegulationsListResponse`

### `GET /api/v1/regulations/categories`
Response model: `BaseResponse`

### `GET /api/v1/regulations/category/{category}`
Response model: `RegulationCategoryResponse`

### `POST /api/v1/regulations/rebuild?force=<bool>`
Response model: `RegulationRebuildResponse`

### `POST /api/v1/regulations/rebuild/async?force=<bool>`
Response model: `BaseResponse` with `data.task_id`

Errors:
- `400` Celery disabled
- `500` Celery task not available

### `GET /api/v1/regulations/status`
Response model: `BaseResponse`

### `GET /api/v1/regulations/search?query=<q>&category=<c>&limit=<1..50>`
Response model: `BaseResponse`

---

## Tasks (Celery)

### `GET /api/v1/tasks/{task_id}`
Response model: `TaskStatusResponse`

Fields:
- `success`
- `message`
- `state` (`PENDING|STARTED|SUCCESS|FAILURE|...`)
- `result` (if ready)
- `task_id`

Errors:
- `400` Celery not enabled
- `500` Celery app/status fetch failure

---

## Authentication and User Management

### `POST /api/v1/auth/register`
Body: `UserCreate`

### `POST /api/v1/auth/login`
Body: `LoginRequest`

Response: `TokenResponse`  
Fields: `access_token`, `refresh_token`, `token_type`, `expires_in`

### `POST /api/v1/auth/refresh`
Input: `refresh_token` (simple parameter; currently accepted as request parameter)

Response: `TokenResponse`

### `POST /api/v1/auth/logout`
Input: `refresh_token` (simple parameter)  
Auth: current authenticated user required.

### `GET /api/v1/auth/me`
Auth: required  
Response: `UserResponse`

### `PUT /api/v1/auth/me`
Auth: active user required  
Body: `UserUpdate`  
Response: `UserResponse`

### `POST /api/v1/auth/change-password`
Auth: active user required  
Body: `PasswordChangeRequest`

### `POST /api/v1/auth/api-keys`
Auth: active user required  
Body: `APIKeyCreate`  
Response: `APIKeyResponse`

### `GET /api/v1/auth/api-keys`
Auth: active user required  
Response: `List[APIKeyResponse]`

### `DELETE /api/v1/auth/api-keys/{key_id}`
Auth: active user required

### `GET /api/v1/auth/users`
Auth: admin required  
Response: `List[UserResponse]`

### `GET /api/v1/auth/audit-logs`
Auth: admin required  
Query:
- `user_id` (optional)
- `event_type` (optional)
- `skip` (default 0)
- `limit` (default 100)

Response: `List[AuditLog]`

---

## WebSocket Contract

## Endpoint

Current effective route:
- `ws://<host>:8000/ws/ws/analysis/{analysis_id}`

Optional auth gate:
- If `REQUIRE_API_KEY=True`:
  - query param: `?api_key=...`
  - or header: `X-API-Key: ...`

## Event Envelope

```json
{
  "type": "connected|progress|complete|error|violation|heartbeat",
  "analysis_id": "string",
  "timestamp": "ISO-8601",
  "schema_version": 1,
  "payload": {}
}
```

Observed progress stages in pipeline:
- `parse`
- `chunk`
- `prompt_gen`
- `llm`
- `violations`
- `reporting`
- `complete`

---

## Webhook Contracts

Current state:
- No dedicated outbound webhook producer endpoint or signed webhook delivery workflow is implemented in the current codebase.

Contract status:
- **Webhook integration contract: Not yet implemented.**

Interim integration options:
- Poll analysis status endpoint.
- Subscribe to WebSocket progress stream.
- Poll Celery task status for async index jobs.

