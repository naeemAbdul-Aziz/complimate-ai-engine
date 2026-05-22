# config/settings.py
"""
Configuration settings for CompliMate AI Engine
==============================================

This module contains all configuration settings, environment variables,
and constants used throughout the application, using Pydantic's BaseSettings.
"""

import secrets
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Performance Presets ---
PERFORMANCE_PRESETS = {
    "fast": {
        "CHUNK_SIZE": 1500,
        "CHUNK_OVERLAP": 100,
        "HYBRID_SEARCH_TOP_K": 3,
        "OPENAI_CONCURRENCY_LIMIT": 20,
    },
    "balanced": {
        "CHUNK_SIZE": 1000,
        "CHUNK_OVERLAP": 200,
        "HYBRID_SEARCH_TOP_K": 5,
        "OPENAI_CONCURRENCY_LIMIT": 10,
    },
    "thorough": {
        "CHUNK_SIZE": 800,
        "CHUNK_OVERLAP": 300,
        "HYBRID_SEARCH_TOP_K": 10,
        "OPENAI_CONCURRENCY_LIMIT": 5,
    }
}

class Settings(BaseSettings):
    """Application settings and configuration, loaded from .env file and environment."""
    
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # API Configuration
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    LOG_LEVEL: str = "INFO"  # Added for logger compatibility
    API_LOG_LEVEL: str = "info"
    CORS_ORIGINS: Any = ["*"]
    
    # Database Configuration
    DATABASE_URL: Optional[str] = None
    DB_ECHO: bool = False
    
    # Redis Configuration
    REDIS_URL: Optional[str] = None
    CACHE_TTL_SECONDS: int = 3600

    # Background Jobs / Celery
    ENABLE_CELERY: bool = False
    CELERY_BROKER_URL: Optional[str] = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: Optional[str] = "redis://localhost:6379/0"

    # Directory Configuration
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    REGULATIONS_DIR: Path = BASE_DIR / "data" / "regulations"
    CONTRACTS_DIR: Path = BASE_DIR / "data" / "contracts"
    VECTOR_STORE_DIR: Path = BASE_DIR / "chroma"
    REPORTS_DIR: Path = BASE_DIR / "reports"
    UPLOADS_DIR: Path = BASE_DIR / "uploads"

    # OpenAI Configuration
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4.1"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"
    SECONDARY_REASONING_MODEL: str = "gpt-4.1"
    ENABLE_SECONDARY_REASONING: bool = True
    OPENAI_REQUEST_TIMEOUT: float = 180.0
    OPENAI_MAX_RETRIES: int = 3
    
    # Secondary reasoning specific controls
    SECONDARY_REASONING_MAX_RETRIES: int = 1
    SECONDARY_REASONING_DEADLINE_SECONDS: float = 90.0
    SECONDARY_REASONING_REQUEST_TIMEOUT: float = 60.0
    SECONDARY_COMPLEXITY_THRESHOLD: int = 40
    SECONDARY_REASONING_MODEL_FAST: str = "gpt-4o"
    # Adaptive refinement controls
    REFINEMENT_TIMEOUT_RATIO_MAX: float = 0.5  # if >50% chunks timeout/error within window, auto-disable temporarily
    # Pinecone Configuration
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_REGION: str = "us-east-1"
    PINECONE_INDEX_NAME: str = "complimate-regulations"
    PINECONE_NAMESPACE: str = "default"
    PINECONE_CLOUD: str = "aws"

    # --- V3: Admin Regulation API ---
    # Secret key for protecting admin-only regulation management endpoints.
    # Should be a long random hex string set in production .env.
    ADMIN_API_KEY: Optional[str] = None

    # --- V3: Cloud Storage (Phase 1 = local, Phase 2 = s3) ---
    CLOUD_STORAGE_PROVIDER: str = "local"   # Options: "local" | "s3"
    MAX_REGULATION_FILE_SIZE_MB: int = 50   # Max upload size for regulation PDFs
    ALLOWED_FILE_EXTENSIONS: tuple = (".pdf", ".txt", ".docx")
    AWS_S3_BUCKET_NAME: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    # Vector Store Configuration
    VECTOR_DB_PROVIDER: str = "chroma"  # Options: "chroma" or "pinecone"

    CHROMA_COLLECTION_NAME: str = "complimate_regulations"
    
    # Document Processing Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    HYBRID_SEARCH_TOP_K: int = 5
    
    # PDF Processing Configuration
    ENABLE_PDF_OCR: bool = False
    OCR_LANG: str = "eng"
    PDF_TEXT_MIN_ALPHA_RATIO: float = 0.2
    PDF_FILTER_MIN_LINE_LEN: int = 12
    PDF_PROGRESS_LOG_EVERY: int = 5
    
    # Regulation Categories
    REGULATION_CATEGORIES: Dict[str, List[str]] = {
        "petroleum": [],
        "mining": [],
        "environmental": [],
        "labor": [],
        "general": []
    }
    
    API_KEY: Optional[str] = None
    
    # JWT Authentication
    JWT_SECRET_KEY: str = secrets.token_urlsafe(48)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Account Security
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 30

    # WebSocket / Realtime
    ENABLE_WEBSOCKETS: bool = True
    MAX_WS_CONNECTIONS: int = 100
    WS_HEARTBEAT_SECONDS: int = 30

    # Rate limiting / circuit breaker
    OPENAI_CONCURRENCY_LIMIT: int = 10
    OPENAI_MAX_TOKENS_PER_MINUTE: int = 60000
    OPENAI_MAX_REQUESTS_PER_MINUTE: int = 60
    CIRCUIT_BREAKER_FAIL_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RESET_SECONDS: int = 120
    SECONDARY_BREAKER_FAIL_THRESHOLD: int = 2
    SECONDARY_BREAKER_RESET_SECONDS: int = 300

    # Deduplication / Grouping Controls
    GROUPING_ENABLED: bool = True
    DEDUPE_SIM_THRESHOLD: float = 0.90
    USE_EMBEDDING_SIMILARITY: bool = False
    MAX_PRUNE_RATIO: float = 0.60
    MIN_ITEMS_AFTER_DEDUPE: int = 1

    # Reporting Enhancements
    REPORT_ENHANCED_MODE: bool = True
    INCLUDE_EXEC_SUMMARY: bool = True
    INCLUDE_MRIA: bool = True

    # PDF / Reporting Font Configuration
    # If USE_UNICODE_FONT is True and UNICODE_FONT_PATH points to a valid TTF file,
    # the report generator will attempt to register and use that font for improved
    # Unicode coverage in PDFs. Falls back gracefully to core fonts if unavailable.
    USE_UNICODE_FONT: bool = False
    UNICODE_FONT_PATH: str = "fonts/DejaVuSans.ttf"

    # Explicit secondary refinement toggle (alias for ENABLE_SECONDARY_REASONING for clarity).
    # Set to False to bypass the secondary reasoning refinement stage even if ENABLE_SECONDARY_REASONING is True.
    SECONDARY_REFINEMENT_ENABLED: bool = True

    # --- Performance & Resource Management ---
    PERFORMANCE_PRESET: str = "balanced"
    ENABLE_MEMORY_PROFILING: bool = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Apply performance preset if not explicitly overridden
        if self.PERFORMANCE_PRESET in PERFORMANCE_PRESETS:
            preset = PERFORMANCE_PRESETS[self.PERFORMANCE_PRESET]
            for key, value in preset.items():
                # Only set if the attribute exists and matches the preset key
                if hasattr(self, key):
                    # In a real scenario, we might check if it was set by env var vs default
                    # For now, we just apply the preset values to the instance
                    setattr(self, key, value)

# Create a single, importable settings instance
settings = Settings()

# Optional getter for settings (for legacy imports)
def get_settings():
    return settings