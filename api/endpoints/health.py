# api/endpoints/health.py
"""
Health check endpoints for CompliMate API
"""

from datetime import datetime
from fastapi import APIRouter

from api.models.schemas import HealthResponse
from config.version import get_version
from engine.regulation_manager import RegulationManager

# Simple singleton pattern for accessing manager state without triggering rebuilds repeatedly
_reg_manager: RegulationManager | None = None

def get_manager() -> RegulationManager:
    global _reg_manager
    if _reg_manager is None:
        _reg_manager = RegulationManager()
    return _reg_manager
from config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint to verify service status."""
    # You can inject the analysis service if needed
    # TODO: Wire actual regulation_loaded flag and index stats once exposed
    mgr = get_manager()
    last_result = getattr(mgr, '_last_rebuild_result', None)
    consecutive_rl = getattr(mgr, '_consecutive_rate_limits', 0)
    cooldown_remaining = None
    cooldown_active = False
    attempt = getattr(mgr, '_last_rebuild_attempt', None)
    if consecutive_rl > 0 and attempt is not None:
        from datetime import datetime as _dt
        now = _dt.utcnow()
        base = mgr._cooldown_seconds_base
        cd = min(base * (2 ** (consecutive_rl - 1)), mgr._max_cooldown_seconds)
        elapsed = (now - attempt).total_seconds()
        if elapsed < cd:
            cooldown_active = True
            cooldown_remaining = int(cd - elapsed)
    # Determine LLM mode (stub vs openai)
    # LLM mode field removed (strict OpenAI usage enforced)
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        regulation_loaded=mgr.regulation_index is not None,
        openai_configured=bool(settings.OPENAI_API_KEY),
        version=get_version(),
        cooldown_active=cooldown_active,
        cooldown_remaining_seconds=cooldown_remaining,
        regulations_indexed=len(mgr.regulations_metadata),
        last_rebuild_status=(last_result or {}).get('status') if last_result else None,
        consecutive_rate_limits=consecutive_rl or None
    )