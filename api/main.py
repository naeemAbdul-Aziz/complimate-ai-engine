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
from api.endpoints.ws import router as ws_router
from api.endpoints.upload import router as upload_router
from api.endpoints.analysis import router as analysis_router
from config import settings
from config.version import get_version
from utils import setup_logging

# Load environment variables
load_dotenv()

# Setup production logging
from config.logger import get_component_logger, create_request_logger
logger = get_component_logger('api')

# Create FastAPI app
app = FastAPI(
    title="CompliMate AI Engine API",
    description="AI-powered contract compliance analysis for Ghana's petroleum sector",
    version=get_version(),
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

# Simple security headers middleware (can be expanded)
from fastapi import Request
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    
    # --- UPDATED CSP ---
    # This is the fix for the blank white screen in Swagger UI.
    # It allows loading scripts/styles from the required CDNs.
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' fastapi.tiangolo.com data:; "
        "connect-src 'self' ws: wss:;"  # Allow 'self' and WebSockets
    )
    response.headers["Content-Security-Policy"] = csp_policy
    
    return response

# Include routers
app.include_router(health_router)
app.include_router(regulations_router)
app.include_router(upload_router)
app.include_router(analysis_router)
if settings.ENABLE_WEBSOCKETS:
    app.include_router(ws_router)

# Serve static frontend and reports
frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
reports_dir = settings.REPORTS_DIR
if frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
if reports_dir.exists():
    app.mount("/reports", StaticFiles(directory=str(reports_dir)), name="reports")

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    try:
        logger.info(f"Starting CompliMate AI Engine API v{get_version()}")
        
        # Ensure required directories exist
        for directory in [settings.UPLOADS_DIR, settings.REPORTS_DIR, settings.VECTOR_STORE_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
        
        logger.info("Required directories created/verified")
        
        # Check OpenAI configuration
        if not settings.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not configured!")
        else:
            logger.info("OpenAI API key configured")
        
        # Detect potential PDF library conflicts (PyPDF2 vs pypdf / fpdf warnings)
        try:
            from importlib import util as importlib_util
            has_pypdf = importlib_util.find_spec('pypdf') is not None
            has_pypdf2 = importlib_util.find_spec('PyPDF2') is not None
            has_pyfpdf = importlib_util.find_spec('fpdf') is not None and importlib_util.find_spec('PyPDF2') is None
            if has_pypdf and has_pypdf2:
                logger.warning(
                    "PDF library conflict: both 'pypdf' and 'PyPDF2' installed. Standardize to one (recommended: 'pypdf'). "
                    "Remediation (Windows PowerShell): pip uninstall PyPDF2; pip install -U pypdf"
                )
            if has_pyfpdf:
                logger.warning(
                    "Legacy 'fpdf' (PyFPDF) detected. If you intended to use 'fpdf2', reinstall: pip uninstall fpdf; pip install fpdf2"
                )
        except Exception:
            pass

        logger.info("CompliMate AI Engine API startup completed")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information."""
    return {
        "message": "CompliMate AI Engine API",
        "version": get_version(),
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
            "upload": "/upload",
            "analysis_start": "/analysis/start",
            "analysis_status": "/analysis/{id}/status",
            "analysis_results": "/analysis/{id}/results",
            "frontend_ui": "/ui",
            "reports": "/reports"
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