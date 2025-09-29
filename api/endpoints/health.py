# api/endpoints/health.py
"""
Health check endpoints for CompliMate API
"""

from datetime import datetime
from fastapi import APIRouter

from api.models.schemas import HealthResponse
from api.services import AnalysisService
from config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint to verify service status."""
    # You can inject the analysis service if needed
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        regulation_loaded=True,  # This should come from the service
        openai_configured=bool(settings.OPENAI_API_KEY),
        version="1.0.0"
    )