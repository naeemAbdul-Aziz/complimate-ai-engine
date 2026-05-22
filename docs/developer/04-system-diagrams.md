# 04 — System Diagrams (ERD, Data Flow, Sequence, Use Case)

## ERD (Core Persistent Entities)

```mermaid
erDiagram
    USER ||--o{ APIKEY : owns
    USER ||--o{ AUDITLOG : generates
    USER ||--o{ REFRESHTOKEN : has

    USER {
        int id PK
        string username
        string email
        string hashed_password
        string role
        bool is_active
        datetime created_at
    }

    APIKEY {
        int id PK
        int user_id FK
        string key_hash
        string key_prefix
        string scopes
        bool is_active
        datetime expires_at
    }

    REFRESHTOKEN {
        int id PK
        int user_id FK
        string token_hash
        bool is_revoked
        datetime expires_at
    }

    AUDITLOG {
        int id PK
        int user_id FK
        string event_type
        string event_description
        bool success
        datetime timestamp
    }

    UPLOADEDFILE {
        string file_id PK
        string original_filename
        string stored_filename
        string file_path
        int file_size
        datetime uploaded_at
    }

    ANALYSIS {
        uuid id PK
        string contract_name
        string file_path
        string status
        string progress
        json results
        json report_paths
        datetime started_at
        datetime completed_at
    }
```

---

## Data Flow Diagram — Contract Analysis

```mermaid
flowchart LR
    U[User / Client] -->|POST upload| API[FastAPI API Layer]
    API --> FS[FileService]
    FS --> UDB[(UploadedFile Table)]
    FS --> UDIR[(uploads/)]

    U -->|POST analysis/start| API
    API --> AS[AnalysisService]
    AS --> ADB[(Analysis Table)]
    AS --> PARSE[engine.parsing]
    PARSE --> RET[engine.retrieval BM25 + Vector]
    RET --> VDB[(Chroma/Pinecone)]
    AS --> LLM[OpenAI LLM Calls]
    AS --> REFINE[engine.reasoning_refinement]
    AS --> REP[reporting.report_generator]
    REP --> RDIR[(reports/)]
    AS --> ADB
    AS --> WS[WebSocket Manager]
    WS --> U
```

---

## Data Flow Diagram — Auth and Access

```mermaid
flowchart LR
    C[Client] -->|register/login| AUTH[Auth Endpoints]
    AUTH --> DB[(User/RefreshToken/APIKey/AuditLog)]
    AUTH -->|JWT + refresh token| C
    C -->|Bearer JWT or API Key| PROT[Protected Endpoints]
    PROT --> DEP[auth dependencies]
    DEP --> DB
```

---

## Sequence Diagram — Upload + Analyze + Result

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant FS as FileService
    participant DB as SQL DB
    participant AS as AnalysisService
    participant ENG as Engine Modules
    participant LLM as OpenAI
    participant WS as WebSocket

    U->>API: POST /api/v1/upload (file)
    API->>FS: upload_file()
    FS->>DB: insert UploadedFile
    FS-->>API: file_id, file_path
    API-->>U: upload response

    U->>API: POST /api/v1/analysis/start {file_id}
    API->>AS: start_analysis()
    AS->>DB: insert Analysis(status=started)
    AS-->>API: analysis_id
    API-->>U: started response

    AS->>DB: set status=running
    AS->>ENG: parse + retrieval + prompt creation
    ENG->>LLM: completion calls
    LLM-->>ENG: responses
    ENG-->>AS: violations/results
    AS->>DB: update results/report_paths/status
    AS->>WS: progress/complete events
    U->>API: GET /api/v1/analysis/{id}/results
    API->>DB: read analysis row
    API-->>U: analysis result payload
```

---

## Sequence Diagram — Auth Login + API Access

```mermaid
sequenceDiagram
    participant C as Client
    participant API as Auth API
    participant AS as AuthService
    participant DB as SQL DB

    C->>API: POST /api/v1/auth/login
    API->>AS: authenticate_user()
    AS->>DB: read user + write audit
    AS-->>API: user authenticated
    API->>AS: create_access_token() + create_refresh_token()
    AS->>DB: persist refresh token
    API-->>C: access_token + refresh_token

    C->>API: Protected endpoint with Bearer token
    API->>AS: decode_access_token()/validate_api_key()
    AS->>DB: user/key verification + audit
    API-->>C: authorized response
```

---

## Use Case Diagram (Functional)

```mermaid
flowchart TB
    Public([Anonymous User])
    User([Authenticated User])
    Analyst([Analyst])
    Admin([Admin])
    Service([Service Client API Key])
    Ops([DevOps Operator])

    UC1((Upload Contract))
    UC2((Start Analysis))
    UC3((Track Status))
    UC4((Get Results))
    UC5((Manage API Keys))
    UC6((View Own Profile))
    UC7((List Users))
    UC8((View Audit Logs))
    UC9((Regulation Rebuild/Search))
    UC10((Configure Deployment))

    Public --> UC1
    Public --> UC2
    Public --> UC3
    Public --> UC4

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5
    User --> UC6
    User --> UC9

    Analyst --> UC1
    Analyst --> UC2
    Analyst --> UC3
    Analyst --> UC4
    Analyst --> UC9

    Admin --> UC7
    Admin --> UC8
    Admin --> UC9
    Admin --> UC5

    Service --> UC3
    Service --> UC4
    Service --> UC9

    Ops --> UC10
```

