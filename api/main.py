# api/main.py
"""
CompliMate AI Engine API v2.0
============================

Modern FastAPI application with modular architecture for contract compliance analysis.
"""

import os
import logging # Already imported
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# --- Ensure Routers are Imported Correctly ---
from api.endpoints.health import router as health_router
from api.endpoints.regulations import router as regulations_router
from api.endpoints.ws import router as ws_router
from api.endpoints.upload import router as upload_router
from api.endpoints.analysis import router as analysis_router
# --- End Router Imports ---

from config import settings
from config.version import get_version # Assuming this exists as per context
# from utils import setup_logging # setup_logging might conflict with logger.py, using logger.py instead

# --- ADDED: Import init_db ---
from api.db import init_db
# --- END ADDED ---

# Load environment variables
load_dotenv()

# Setup production logging using logger.py
from config.logger import get_component_logger # Use the component logger
logger = get_component_logger('api.main') # Name it appropriately

# Create FastAPI app
app = FastAPI(
    title="CompliMate AI Engine API",
    description="AI-powered contract compliance analysis for Ghana's petroleum sector",
    version=get_version(), # Use the version function
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for frontend access
# Check settings format for CORS_ORIGINS
cors_origins = settings.CORS_ORIGINS
if isinstance(settings.CORS_ORIGINS, str):
    cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(',') if origin.strip()]
elif not isinstance(settings.CORS_ORIGINS, list):
    cors_origins = ["*"] # Default fallback if format is wrong

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins, # Use the processed list
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

    # --- Use the updated CSP from the provided context ---
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' fastapi.tiangolo.com data:; "
        "connect-src 'self' ws: wss:;" # Allow 'self' and WebSockets
    )
    response.headers["Content-Security-Policy"] = csp_policy

    return response

# --- ADDED: Startup Event Handler ---
@app.on_event("startup")
async def on_startup():
    """
    Run on application startup.
    This creates all database tables defined with SQLModel.
    """
    logger.info("Initializing database...")
    await init_db() # Call the init_db function from api.db
    logger.info("Database initialization complete.")

    # --- Moved startup logging here ---
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

        # PDF library conflict detection (copied from context)
        try:
            from importlib import util as importlib_util
            has_pypdf = importlib_util.find_spec('pypdf') is not None
            # requirements.txt uses PyPDF2, check for that specifically
            has_pypdf2 = importlib_util.find_spec('PyPDF2') is not None
            # reporting/report_generator uses fpdf
            has_fpdf = importlib_util.find_spec('fpdf') is not None
            # Check for fpdf2 just in case
            has_fpdf2 = importlib_util.find_spec('fpdf2') is not None

            # Logic needs adjustment based on actual libraries used
            # PyPDF2 is in requirements, fpdf is used in reporting
            # No direct conflict mentioned, but potential confusion.
            # Let's log what's found:
            pdf_libs = []
            if has_pypdf: pdf_libs.append("pypdf")
            if has_pypdf2: pdf_libs.append("PyPDF2")
            if has_fpdf: pdf_libs.append("fpdf (PyFPDF)")
            if has_fpdf2: pdf_libs.append("fpdf2")
            logger.info(f"Detected PDF libraries: {', '.join(pdf_libs)}")
            # Keep original warning logic if needed, but adapt based on project needs
            # The TROUBLESHOOTING.md suggests standardizing on pypdf, but requirements use PyPDF2.
            # Sticking to just logging for now.

        except Exception as pdf_check_e:
            logger.warning(f"Could not perform PDF library check: {pdf_check_e}")

        logger.info("CompliMate AI Engine API startup completed")

    except Exception as e:
        logger.critical(f"CRITICAL Error during startup sequence: {e}", exc_info=True)
        # Depending on severity, you might want to raise here to stop startup
        # raise e
# --- END ADDED ---

# Include routers
app.include_router(health_router, prefix="/api/v1", tags=["Health"]) # Added prefix/tags based on user structure
app.include_router(regulations_router, prefix="/api/v1/regulations", tags=["Regulations"]) # Added prefix/tags based on user structure
app.include_router(upload_router, prefix="/api/v1", tags=["File Upload"]) # Added prefix/tags based on user structure
app.include_router(analysis_router, prefix="/api/v1/analysis", tags=["Analysis"]) # Added prefix/tags based on user structure
if settings.ENABLE_WEBSOCKETS:
    app.include_router(ws_router, prefix="/ws", tags=["WebSocket"]) # Added prefix/tags based on user structure

# Serve static frontend and reports (Paths adjusted based on settings and context)
frontend_dir = settings.BASE_DIR / "frontend" # Get frontend path relative to BASE_DIR
reports_dir = settings.REPORTS_DIR # Use settings for reports dir
uploads_dir = settings.UPLOADS_DIR # Mount uploads dir as well

if frontend_dir.exists():
    # Mount at root to serve index.html by default? Or keep /ui? Keep /ui as per context.
    app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Serving frontend static files from: {frontend_dir}")
else:
    logger.warning(f"Frontend directory not found: {frontend_dir}")

if reports_dir.exists():
    app.mount("/reports", StaticFiles(directory=str(reports_dir)), name="reports")
    logger.info(f"Serving reports static files from: {reports_dir}")
else:
    logger.warning(f"Reports directory not found: {reports_dir}")

if uploads_dir.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
    logger.info(f"Serving uploads static files from: {uploads_dir}")
else:
    logger.warning(f"Uploads directory not found: {uploads_dir}")

@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information."""
    # Use the structure from the provided context's api/main.py
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
            "health": "/api/v1/health", # Corrected paths based on router prefixes
            "regulations": "/api/v1/regulations",
            "upload": "/api/v1/upload",
            "analysis_start": "/api/v1/analysis/start",
            "analysis_status": "/api/v1/analysis/{id}/status",
            "analysis_results": "/api/v1/analysis/{id}/results",
            "frontend_ui": "/ui",
            "reports": "/reports"
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Attempting to start Uvicorn on {settings.API_HOST}:{settings.API_PORT}")
    uvicorn.run(
        "api.main:app", # Correct path to the app instance
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.API_LOG_LEVEL.lower() # Ensure log level is lowercase
    )