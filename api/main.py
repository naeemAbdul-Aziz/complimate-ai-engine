# api/main.py
"""
Main FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from config.logger import get_component_logger
from config.version import get_project_version
from api.endpoints import analysis, health, regulations, upload, ws

# --- ADDED ---
from api.db import init_db
# --- END ADDED ---

# Get logger
logger = get_component_logger("api")

# Create application
app = FastAPI(
    title="CompliMate AI Engine",
    description="API for contract compliance analysis using RAG.",
    version=get_project_version()
)

# --- ADDED: Startup Event Handler ---
@app.on_event("startup")
async def on_startup():
    """
    Run on application startup.
    This creates all database tables defined with SQLModel.
    """
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization complete.")
# --- END ADDED ---


# --- Mount static directories ---
# Mount uploads directory for serving uploaded files
(settings.UPLOADS_DIR).mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOADS_DIR), name="uploads")

# Mount reports directory for serving generated reports
(settings.REPORTS_DIR).mkdir(exist_ok=True)
app.mount("/reports", StaticFiles(directory=settings.REPORTS_DIR), name="reports")

# Mount frontend directory
app.mount("/static", StaticFiles(directory=settings.BASE_DIR / "frontend"), name="static")


# --- Include API routers ---
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(upload.router, prefix="/api/v1", tags=["File Upload"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(regulations.router, prefix="/api/v1/regulations", tags=["Regulations"])
app.include_router(ws.router, prefix="/ws", tags=["WebSocket"])


# --- Configure CORS ---
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {settings.CORS_ORIGINS}")

# --- Root endpoint ---
@app.get("/")
async def read_root():
    """Root endpoint providing basic API info."""
    return {
        "message": "Welcome to the CompliMate AI Engine API",
        "version": get_project_version(),
        "docs": "/docs",
        "redoc": "/redoc"
    }

# --- Main entry point for uvicorn ---
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting CompliMate API v{get_project_version()} on {settings.API_HOST}:{settings.API_PORT}")
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.API_LOG_LEVEL.lower()
    )