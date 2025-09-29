# config/settings.py
"""
Configuration settings for CompliMate AI Engine
==============================================

This module contains all configuration settings, environment variables,
and constants used throughout the application.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    """Application settings and configuration."""
    
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_RELOAD: bool = os.getenv("API_RELOAD", "True").lower() == "true"
    API_LOG_LEVEL: str = os.getenv("API_LOG_LEVEL", "info")
    
    # OpenAI Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    OPENAI_REQUEST_TIMEOUT: float = float(os.getenv("OPENAI_REQUEST_TIMEOUT", "180.0"))
    OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    
    # File paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOADS_DIR: Path = BASE_DIR / "uploads"
    REPORTS_DIR: Path = BASE_DIR / "reports"
    REGULATIONS_DIR: Path = DATA_DIR / "regulations"
    CONTRACT_FOLDER: Path = DATA_DIR / "contracts"
    VECTOR_STORE_DIR: Path = BASE_DIR / "vector_store"
    
    # Legacy single regulation file (for backward compatibility)
    REGULATION_FILE: Path = REGULATIONS_DIR / "li_2204.pdf"
    
    # Analysis Configuration
    MAX_CONCURRENT_ANALYSES: int = int(os.getenv("MAX_CONCURRENT_ANALYSES", "5"))
    ANALYSIS_TIMEOUT_MINUTES: int = int(os.getenv("ANALYSIS_TIMEOUT_MINUTES", "30"))
    HYBRID_SEARCH_TOP_K: int = int(os.getenv("HYBRID_SEARCH_TOP_K", "5"))
    
    # Vector Storage Configuration
    USE_PERSISTENT_STORAGE: bool = os.getenv("USE_PERSISTENT_STORAGE", "True").lower() == "true"
    VECTOR_STORE_TYPE: str = os.getenv("VECTOR_STORE_TYPE", "chroma")  # "chroma" or "memory"
    CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "ghana_regulations")
    
    # Multi-regulation Configuration
    REGULATION_CATEGORIES: dict = {
        "petroleum": ["li_2204.pdf"],
        "mining": [],
        "environmental": [],
        "labor": [],
        "general": []
    }
    
    # Regulation Processing
    CHUNK_SIZE: int = int(os.getenv("REGULATION_CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP: int = int(os.getenv("REGULATION_CHUNK_OVERLAP", "200"))
    ENABLE_METADATA_EXTRACTION: bool = os.getenv("ENABLE_METADATA_EXTRACTION", "True").lower() == "true"
    
    # File Upload Configuration
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    ALLOWED_FILE_EXTENSIONS: tuple = ('.pdf', '.txt', '.docx')
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Security Configuration
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "3600"))  # seconds
    
    # Database Configuration (for future use)
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    DB_ECHO: bool = os.getenv("DB_ECHO", "False").lower() == "true"
    
    # Redis Configuration (for caching)
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration settings."""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        # Create directories if they don't exist
        for directory in [cls.DATA_DIR, cls.UPLOADS_DIR, cls.REPORTS_DIR]:
            directory.mkdir(exist_ok=True, parents=True)
        
        # Check if regulation file exists
        if not cls.REGULATION_FILE.exists():
            raise FileNotFoundError(f"Regulation file not found: {cls.REGULATION_FILE}")

# Create settings instance
settings = Settings()

# Environment-specific configurations
class DevelopmentSettings(Settings):
    """Development-specific settings."""
    API_RELOAD = True
    LOG_LEVEL = "DEBUG"

class ProductionSettings(Settings):
    """Production-specific settings."""
    API_RELOAD = False
    LOG_LEVEL = "INFO"
    API_HOST = "0.0.0.0"

class TestingSettings(Settings):
    """Testing-specific settings."""
    LOG_LEVEL = "WARNING"
    UPLOADS_DIR = Path("/tmp/complimate_test_uploads")
    REPORTS_DIR = Path("/tmp/complimate_test_reports")

# Factory function to get settings based on environment
def get_settings() -> Settings:
    """Get settings based on environment."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return ProductionSettings()
    elif env == "testing":
        return TestingSettings()
    else:
        return DevelopmentSettings()