# api/main.py
"""
CompliMate AI Engine API v2.0
============================

Modern FastAPI application with modular architecture for contract compliance analysis.
"""

import os
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from dotenv import load_dotenv

from api.error_handlers import http_exception_handler, general_exception_handler
from api.db import init_db
from config import settings
from config.version import get_version
from config.logger import get_component_logger

# --- Ensure Routers are Imported Correctly ---
from api.endpoints.health import router as health_router
from api.endpoints.regulations import router as regulations_router
from api.endpoints.ws import router as ws_router
from api.endpoints.upload import router as upload_router
from api.endpoints.analysis import router as analysis_router
from api.endpoints.auth import router as auth_router
from api.endpoints.tasks import router as tasks_router

# Load environment variables
load_dotenv()

# Setup logging
logger = get_component_logger('api.main')

# Create FastAPI app
app = FastAPI(
    title="CompliMate AI Engine API",
    description="AI-powered contract compliance analysis for Ghana's petroleum sector",
    version=get_version(),
    docs_url="/docs",
    redoc_url="/redoc",
    exception_handlers={
        HTTPException: http_exception_handler,
        Exception: general_exception_handler,
    }
)

# CORS middleware
cors_origins = settings.CORS_ORIGINS
if isinstance(settings.CORS_ORIGINS, str):
    cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(',') if origin.strip()]
elif not isinstance(settings.CORS_ORIGINS, list):
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip compression for responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"

    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' fastapi.tiangolo.com data:; "
        "connect-src 'self' ws: wss:;"
    )
    response.headers["Content-Security-Policy"] = csp_policy
    return response

# --- Startup Event Handler ---
@app.on_event("startup")
async def on_startup():
    """
    Run on application startup.
    This creates all database tables defined with SQLModel.
    """
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization complete.")

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

        # PDF library check
        try:
            from importlib import util as importlib_util
            has_pypdf = importlib_util.find_spec('pypdf') is not None
            has_fpdf2 = importlib_util.find_spec('fpdf2') is not None
            logger.info(f"PDF libraries check: pypdf (reader) found: {has_pypdf}, fpdf2 (writer) found: {has_fpdf2}")
            if not has_pypdf or not has_fpdf2:
                logger.warning("A required PDF library is missing. Please run 'pip install pypdf fpdf2'")
        except Exception as pdf_check_e:
            logger.warning(f"Could not perform PDF library check: {pdf_check_e}")

        # Log registered routes
        try:
            route_paths = []
            for r in app.routes:
                try:
                    route_paths.append(getattr(r, 'path', str(r)))
                except Exception:
                    route_paths.append(str(r))
            logger.info(f"Registered routes ({len(route_paths)}): {route_paths}")
        except Exception as route_log_e:
            logger.warning(f"Could not enumerate routes: {route_log_e}")

        logger.info("CompliMate AI Engine API startup completed")

    except Exception as e:
        logger.critical(f"CRITICAL Error during startup sequence: {e}", exc_info=True)

# Include routers
app.include_router(health_router, prefix="/api/v1", tags=["Health"])
app.include_router(regulations_router, prefix="/api/v1/regulations", tags=["Regulations"])
app.include_router(upload_router, prefix="/api/v1", tags=["File Upload"])
app.include_router(analysis_router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(tasks_router, prefix="/api/v1", tags=["Tasks"])

if settings.ENABLE_WEBSOCKETS:
    app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

# Serve static files
frontend_dir = settings.BASE_DIR / "frontend"
reports_dir = settings.REPORTS_DIR
uploads_dir = settings.UPLOADS_DIR

if frontend_dir.exists():
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
            "health": "/api/v1/health",
            "regulations": "/api/v1/regulations",
            "upload": "/api/v1/upload",
            "analysis_start": "/api/v1/analysis/start",
            "analysis_status": "/api/v1/analysis/{id}/status",
            "analysis_results": "/api/v1/analysis/{id}/results",
            "regulation_rebuild_async": "/api/v1/regulations/rebuild/async",
            "regulation_search": "/api/v1/regulations/search",
            "task_status": "/api/v1/tasks/{task_id}",
            "frontend_ui": "/ui",
            "reports": "/reports"
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Attempting to start Uvicorn on {settings.API_HOST}:{settings.API_PORT}")
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.API_LOG_LEVEL.lower()
    )