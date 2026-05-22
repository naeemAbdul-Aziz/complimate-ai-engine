# CompliMate AI Engine — Implementation Plan (V2, Historical)

> [!IMPORTANT]
> **This document is superseded by the V3 Final Plan (2026-05-22).**
> The V3 architecture moves to Pinecone-first cloud-native storage, a dedicated Admin Regulation API,
> and zero-downtime hot-path isolation. See `implementation_plan_v3_final.md` in the brain artifacts
> and the V3 entry in `docs/CHANGELOG.md` for the current active plan.

## Overview (V2 — Historical Reference)
This document outlines the V2 implementation plan for security hardening, production infrastructure, pagination, job management, and performance optimization. Many items below have since been completed. Refer to V3 for the current roadmap.

---

## 1. 🔐 Security Hardening (Authentication & Authorization)

### Phase 1: JWT Authentication System
**Timeline: 2-3 days**

#### Implementation Steps:
1. **Install Dependencies**
   ```bash
   pip install python-jose[cryptography] passlib[bcrypt] python-multipart
   ```

2. **Create Auth Models & Schemas**
   ```python
   # api/models/auth_models.py
   class User(SQLModel, table=True):
       id: Optional[int] = Field(default=None, primary_key=True)
       username: str = Field(unique=True, index=True)
       email: str = Field(unique=True, index=True)
       hashed_password: str
       is_active: bool = Field(default=True)
       role: str = Field(default="user")  # user, admin, analyst
       created_at: datetime = Field(default_factory=datetime.utcnow)
   ```

3. **JWT Token System**
   ```python
   # api/services/auth_service.py
   - JWT token generation/validation
   - Password hashing (bcrypt)
   - User authentication endpoints
   - Role-based access control (RBAC)
   ```

4. **Auth Middleware & Dependencies**
   ```python
   # api/dependencies/auth.py
   - get_current_user dependency
   - require_role decorator
   - API key validation fallback
   ```

5. **Protected Endpoints**
   - Secure all analysis endpoints
   - Admin-only user management
   - Role-based feature access

#### Security Features:
- **Access Tokens**: 15-minute expiry
- **Refresh Tokens**: 7-day expiry with rotation
- **Rate Limiting**: Per-user and per-IP limits
- **Password Policy**: Min 8 chars, complexity requirements
- **Session Management**: Token blacklist for logout

### Phase 2: Advanced Security
**Timeline: 1-2 days**

- **API Key Management**: Multiple keys, scoped permissions
- **Request Signing**: HMAC verification for sensitive operations
- **Audit Logging**: All auth events, failed attempts
- **CSRF Protection**: For web interface
- **Input Sanitization**: Enhanced validation

---

## 2. 🏗️ Production Infrastructure (PostgreSQL + Redis Clusters)

### Phase 1: Database Migration
**Timeline: 2-3 days**

#### PostgreSQL Setup:
1. **Production Database Schema**
   ```sql
   -- Create optimized indexes
   CREATE INDEX CONCURRENTLY idx_analysis_status ON analysis(status);
   CREATE INDEX CONCURRENTLY idx_analysis_created ON analysis(created_at);
   CREATE INDEX CONCURRENTLY idx_files_analysis ON files(analysis_id);
   ```

2. **Connection Pooling**
   ```python
   # config/database.py
   from sqlalchemy.pool import QueuePool
   
   engine = create_async_engine(
       DATABASE_URL,
       poolclass=QueuePool,
       pool_size=20,
       max_overflow=30,
       pool_pre_ping=True,
       pool_recycle=3600
   )
   ```

3. **Migration System**
   ```python
   # Use Alembic for schema migrations
   pip install alembic
   alembic init migrations
   # Create migration scripts for existing tables
   ```

#### Redis Cluster Configuration:
1. **Cluster Setup**
   ```yaml
   # docker-compose.prod.yml
   redis-cluster:
     image: redis/redis-stack-server:latest
     deploy:
       replicas: 3
     environment:
       REDIS_CLUSTER_ENABLED: yes
   ```

2. **High Availability Caching**
   ```python
   # utils/redis_cluster.py
   import redis.sentinel
   
   sentinels = [('redis-1', 26379), ('redis-2', 26379)]
   sentinel = redis.sentinel.Sentinel(sentinels)
   redis_client = sentinel.master_for('mymaster')
   ```

### Phase 2: Container Orchestration
**Timeline: 1-2 days**

#### Kubernetes Deployment:
```yaml
# k8s/app-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: complimate-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: api
        image: complimate-ai:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
```

#### Infrastructure as Code:
- **Terraform**: AWS/Azure resource provisioning
- **Ansible**: Configuration management
- **CI/CD Pipeline**: GitHub Actions deployment

---

## 3. 📄 Pagination Implementation

### Phase 1: Backend Pagination
**Timeline: 1 day**

#### Database Pagination:
```python
# api/services/pagination_service.py
from sqlalchemy import func
from typing import Generic, TypeVar, List

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int
    has_next: bool
    has_prev: bool

async def paginate_query(
    session: AsyncSession,
    query: Select,
    page: int = 1,
    per_page: int = 20
) -> PaginatedResponse:
    # Count total items
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query)
    
    # Apply pagination
    offset = (page - 1) * per_page
    items = await session.execute(
        query.offset(offset).limit(per_page)
    )
    
    return PaginatedResponse(
        items=items.scalars().all(),
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page),
        has_next=page * per_page < total,
        has_prev=page > 1
    )
```

#### Paginated Endpoints:
```python
# api/endpoints/analysis.py
@router.get("/analyses", response_model=PaginatedResponse[AnalysisResponse])
async def list_analyses(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session)
):
    query = select(Analysis)
    if status:
        query = query.where(Analysis.status == status)
    
    return await paginate_query(session, query, page, per_page)
```

### Phase 2: Frontend Pagination
**Timeline: 1 day**

#### JavaScript Pagination Component:
```javascript
// frontend/js/pagination.js
class PaginationController {
    constructor(apiEndpoint, container, itemRenderer) {
        this.apiEndpoint = apiEndpoint;
        this.container = container;
        this.itemRenderer = itemRenderer;
        this.currentPage = 1;
        this.perPage = 20;
    }
    
    async loadPage(page = 1) {
        const response = await fetch(
            `${this.apiEndpoint}?page=${page}&per_page=${this.perPage}`
        );
        const data = await response.json();
        
        this.renderItems(data.items);
        this.renderPagination(data);
    }
}
```

---

## 4. 🔄 Job Management & Background Tasks

### Phase 1: Task Queue Implementation
**Timeline: 2-3 days**

#### Celery Integration:
```python
# Install dependencies
pip install celery[redis] flower

# tasks/celery_app.py
from celery import Celery

celery_app = Celery(
    'complimate_tasks',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['tasks.analysis_tasks', 'tasks.report_tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
)
```

#### Background Task Models:
```python
# api/models/task_models.py
class TaskResult(SQLModel, table=True):
    id: str = Field(primary_key=True)  # Celery task ID
    status: str  # PENDING, STARTED, SUCCESS, FAILURE, RETRY
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    progress: int = Field(default=0)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

#### Task Definitions:
```python
# tasks/analysis_tasks.py
@celery_app.task(bind=True)
def analyze_contract_async(self, file_id: int, user_id: int):
    try:
        # Update task status
        self.update_state(state='STARTED', meta={'progress': 0})
        
        # Perform analysis with progress updates
        result = perform_analysis(file_id, progress_callback=lambda p: 
            self.update_state(state='PROGRESS', meta={'progress': p})
        )
        
        return {'result': result, 'file_id': file_id}
    except Exception as exc:
        self.update_state(
            state='FAILURE',
            meta={'error': str(exc), 'traceback': traceback.format_exc()}
        )
        raise
```

### Phase 2: Job Monitoring Dashboard
**Timeline: 1-2 days**

#### Task Status API:
```python
# api/endpoints/tasks.py
@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    
    return {
        'task_id': task_id,
        'status': result.status,
        'result': result.result,
        'progress': result.info.get('progress', 0) if result.info else 0
    }

@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    celery_app.control.revoke(task_id, terminate=True)
    return {'message': f'Task {task_id} cancelled'}
```

#### Flower Dashboard:
```bash
# Start Flower for task monitoring
celery -A tasks.celery_app flower --port=5555
```

---

## 5. ⚡ Performance Optimization

### Phase 1: Database Optimization
**Timeline: 1-2 days**

#### Query Optimization:
```python
# Optimized queries with eager loading
query = (
    select(Analysis)
    .options(selectinload(Analysis.files))
    .options(selectinload(Analysis.violations))
    .where(Analysis.user_id == user_id)
)

# Add database indexes
CREATE INDEX CONCURRENTLY idx_analysis_user_status ON analysis(user_id, status);
CREATE INDEX CONCURRENTLY idx_violations_analysis ON violations(analysis_id);
```

#### Connection Pooling:
```python
# config/database.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False  # Disable in production
)
```

### Phase 2: Advanced Caching
**Timeline: 1 day**

#### Multi-Level Caching:
```python
# utils/advanced_cache.py
class MultiLevelCache:
    def __init__(self):
        self.l1_cache = {}  # In-memory
        self.l2_cache = redis_client  # Redis
        
    async def get(self, key: str):
        # L1 cache check
        if key in self.l1_cache:
            return self.l1_cache[key]
            
        # L2 cache check
        value = await self.l2_cache.get(key)
        if value:
            self.l1_cache[key] = json.loads(value)
            return self.l1_cache[key]
            
        return None
```

#### Smart Cache Invalidation:
```python
# Cache invalidation on data changes
@cache_invalidate_on_update('analysis:{analysis_id}')
async def update_analysis(analysis_id: int, updates: dict):
    # Update logic
    pass
```

### Phase 3: Performance Monitoring
**Timeline: 1 day**

#### APM Integration:
```python
# Install APM tools
pip install prometheus-client psutil

# metrics/performance.py
from prometheus_client import Counter, Histogram, Gauge

request_count = Counter('http_requests_total', 'Total HTTP requests')
response_time = Histogram('http_request_duration_seconds', 'HTTP request duration')
active_connections = Gauge('active_db_connections', 'Active database connections')
```

---

## Implementation Timeline

### Sprint 1 (Week 1): Security Foundation
- [ ] JWT Authentication System
- [ ] User Management API
- [ ] Role-Based Access Control
- [ ] Rate Limiting Enhancement

### Sprint 2 (Week 2): Infrastructure & Scaling
- [ ] PostgreSQL Migration
- [ ] Redis Cluster Setup
- [ ] Container Orchestration
- [ ] Database Optimization

### Sprint 3 (Week 3): Features & Monitoring
- [ ] Pagination Implementation
- [ ] Job Management System
- [ ] Performance Monitoring
- [ ] Task Dashboard

### Sprint 4 (Week 4): Testing & Production
- [ ] Load Testing
- [ ] Security Auditing
- [ ] Production Deployment
- [ ] Documentation Updates

---

## Success Metrics

### Security:
- Zero unauthorized access attempts succeed
- All endpoints require proper authentication
- Audit logs capture all security events

### Performance:
- 95% of API requests complete under 200ms
- Database queries optimized (no N+1 problems)
- Cache hit ratio above 80%

### Scalability:
- System handles 1000+ concurrent users
- Background tasks process without blocking API
- Database supports 10x current data volume

### Reliability:
- 99.9% uptime
- Automatic failover for database/cache
- All background jobs complete successfully or retry appropriately

---

**Next Steps**: Choose which sprint to start with based on your immediate priorities and team capacity.