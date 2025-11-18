# config/settings.py
"""
Configuration settings for CompliMate AI Engine
==============================================

This module contains all configuration settings, environment variables,
and constants used throughout the application, using Pydantic's BaseSettings.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings and configuration, loaded from .env file and environment."""
    
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # API Configuration
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    API_LOG_LEVEL: str = "info"
    
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
    
    # File paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOADS_DIR: Path = BASE_DIR / "uploads"
    REPORTS_DIR: Path = BASE_DIR / "reports"
    REGULATIONS_DIR: Path = DATA_DIR / "regulations"
    CONTRACT_FOLDER: Path = DATA_DIR / "contracts"
    VECTOR_STORE_DIR: Path = BASE_DIR / "vector_store"
    
    # Legacy single regulation file
    REGULATION_FILE: Path = REGULATIONS_DIR / "li_2204.pdf"
    
    # Analysis Configuration
    MAX_CONCURRENT_ANALYSES: int = 5
    ANALYSIS_TIMEOUT_MINUTES: int = 30
    HYBRID_SEARCH_TOP_K: int = 5
    
    # Vector Storage Configuration
    USE_PERSISTENT_STORAGE: bool = True
    VECTOR_STORE_TYPE: str = "chroma"
    CHROMA_COLLECTION_NAME: str = "ghana_regulations"
    VECTOR_DB_PROVIDER: str = "chroma"
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_INDEX_NAME: str = "complimate-regulations"
    PINECONE_NAMESPACE: str = "default"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    
    # Multi-regulation Configuration
    REGULATION_CATEGORIES: Dict[str, Any] = {
        "petroleum": ["li_2204.pdf"],
    }
    
    # Regulation Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    ENABLE_METADATA_EXTRACTION: bool = True
    
    # File Upload Configuration
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_FILE_EXTENSIONS: tuple = ('.pdf', '.txt', '.docx')
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Security Configuration
    CORS_ORIGINS: List[str] = ["*"]
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 3600
    REQUIRE_API_KEY: bool = False
    API_KEY: Optional[str] = None
    
    # JWT Authentication
    import secrets
    _jwt_default = secrets.token_urlsafe(48)
    JWT_SECRET_KEY: str = _jwt_default
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

# Create a single, importable settings instance
settings = Settings()
# Optional getter for settings (for legacy imports)
def get_settings():
    return settings