# api/main.py
"""
CompliMate AI Engine API v2.0
============================

Modern FastAPI application with modular architecture for contract compliance analysis.
"""

import os
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from api.endpoints.health import router as health_router
from api.endpoints.regulations import router as regulations_router
from config import settings
from utils import setup_logging

# Load environment variables
load_dotenv()

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="CompliMate AI Engine API",
    description="AI-powered contract compliance analysis for Ghana's petroleum sector",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(regulations_router)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    try:
        logger.info("Starting CompliMate AI Engine API v2.0.0")
        
        # Ensure required directories exist
        for directory in [settings.UPLOADS_DIR, settings.REPORTS_DIR, settings.VECTOR_STORE_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
        
        logger.info("Required directories created/verified")
        
        # Check OpenAI configuration
        if not settings.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not configured!")
        else:
            logger.info("OpenAI API key configured")
        
        logger.info("CompliMate AI Engine API startup completed")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information."""
    return {
        "message": "CompliMate AI Engine API",
        "version": "2.0.0",
        "description": "AI-powered contract compliance analysis for Ghana's petroleum sector",
        "features": [
            "Multi-regulation support",
            "Persistent vector storage", 
            "Advanced regulation management",
            "Comprehensive compliance analysis"
        ],
        "docs": "/docs",
        "endpoints": {
            "health": "/health", 
            "regulations": "/regulations",
            "analysis": "/analysis (coming soon)"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.API_LOG_LEVEL
    )