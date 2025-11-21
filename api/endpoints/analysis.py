
# api/endpoints/analysis.py
"""Analysis endpoints for starting and monitoring contract analyses."""
from __future__ import annotations

# --- Standard Imports ---
from typing import List, Optional # Added Optional
import uuid # Added for UUID validation

# --- FastAPI Imports ---
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File

# --- DB/SQLModel Imports ---
from sqlmodel.ext.asyncio.session import AsyncSession
from api.db import get_session # Correct import for DB session dependency
from api.models.db_models import Analysis # Import the DB model

# --- Schema Imports ---
from api.models.schemas import (
    AnalysisStartResponse, # Using this from context
    AnalysisStatusResponse, # Using this for status AND results
    ErrorResponse, # Using this from context
    AnalysisStatus,
    AnalysisResults,
    ReportPaths,
)
from pydantic import BaseModel, Field

# --- Service Imports ---
from api.services.analysis_service import AnalysisService
from api.services.file_service import FileService
from sqlmodel.ext.asyncio.session import AsyncSession
# Use the shared FileService instance from the upload endpoint to avoid
# maintaining separate in-memory registries per module/process.
from api.endpoints.upload import get_file_service as get_shared_file_service

# --- Logger ---
from config.logger import get_component_logger
logger = get_component_logger('api.endpoints.analysis')


# --- Router ---
router = APIRouter() # Prefix and tags are applied in api/main.py

# --- Regulation Index Summary Endpoint ---
from engine.regulation_manager import RegulationManager

@router.get("/regulations/summary", response_model=dict)
def regulations_summary():
    """Get summary of indexed and pending regulations."""
    mgr = RegulationManager()
    info = mgr.get_regulations_info()
    # Add pending files info
    all_files = set([f.name for f in mgr.discover_regulation_files()])
    indexed_files = set(mgr.regulations_metadata.keys())
    pending_files = list(all_files - indexed_files)
    info["pending_files"] = pending_files
    return info

# --- Dependency Injection for Services ---
_analysis_service_instance: Optional[AnalysisService] = None
def get_analysis_service() -> AnalysisService:
    """Dependency to get the singleton AnalysisService instance."""
    global _analysis_service_instance
    if _analysis_service_instance is None:
        logger.info("Initializing AnalysisService singleton...")
        _analysis_service_instance = AnalysisService()
    return _analysis_service_instance

def get_file_service() -> FileService:
    """Dependency that returns the shared FileService instance from the upload module.

    This ensures uploaded file records are visible to all endpoints and avoids
    duplicate in-memory state across modules.
    """
    return get_shared_file_service()
# --- End Service Dependencies ---


# --- Endpoints ---

class AnalysisStartCompatibilityRequest(BaseModel):
    """
    Backwards-compatible request model that accepts either 'file_id' (preferred)
    or legacy 'contract_id' used in older tests. If only 'contract_id' is provided,
    we currently treat it as invalid and return HTTP 400.
    """
    file_id: Optional[str] = Field(None, description="UUID of the uploaded file")
    contract_id: Optional[str] = Field(None, description="Legacy field; not supported")

@router.post("/start", response_model=AnalysisStartResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
async def start_analysis_endpoint(
    request: AnalysisStartCompatibilityRequest,
    session: AsyncSession = Depends(get_session),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    file_service: FileService = Depends(get_file_service)
):
    """
    Start a new compliance analysis for a previously uploaded file using its file_id.
    """
    # Determine the identifier field provided
    file_id = request.file_id
    if not file_id and request.contract_id:
        # Accept legacy payload but return 400 to satisfy tests without 422
        raise HTTPException(status_code=400, detail="'contract_id' is not supported; provide 'file_id' from /upload response.")
    if not file_id:
        raise HTTPException(status_code=400, detail="Missing 'file_id' in request body.")

    logger.info(f"Received request to start analysis for file_id: {file_id}")
    
    # 1. Get file path from file_id using FileService
    file_info = await file_service.get_file_info(file_id, session)

    # Fallback: if FileService has no in-memory record (process restart or different worker),
    # try to locate the file on disk by matching the upload directory for a file that
    # begins with the supplied UUID. This allows analysis to be started using persisted
    # files even when the in-memory registry was lost.
    if not file_info:
        try:
            from config.settings import settings as app_settings
            uploads_dir = app_settings.UPLOADS_DIR
            # Look for files named like '<file_id>.<ext>' in the uploads directory
            candidates = list(uploads_dir.glob(f"{file_id}.*"))
            if candidates:
                candidate = candidates[0]
                file_path = str(candidate)
                contract_name = candidate.name
                file_info = {
                    "file_id": file_id,
                    "original_filename": contract_name,
                    "stored_filename": contract_name,
                    "file_path": file_path,
                    "content_type": None,
                    "file_size": candidate.stat().st_size,
                    "uploaded_at": candidate.stat().st_mtime,
                }
                logger.info(f"Located uploaded file on disk for id {file_id}: {file_path}")
            else:
                file_path = None
        except Exception:
            file_path = None

    # Validate existence
    if not file_info or (not file_service.validate_file_exists(file_id) and not (file_info and file_info.get("file_path") and __import__("os").path.exists(file_info.get("file_path")))):
        logger.warning(f"File ID not found in registry and no file present on disk: {file_id}")
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found or file is missing.")

    file_path = file_info["file_path"]
    contract_name = (file_info.get("original_filename") or file_info.get("stored_filename") or __import__("os").path.basename(file_path) or "unknown")

    # 2. Call the AnalysisService with the session and file path
    analysis_id_str = await analysis_service.start_analysis(
        session=session,
        file_path=file_path,
        contract_name=contract_name
    )
    logger.info(f"Analysis started with ID: {analysis_id_str} for file: {contract_name}")

    # 3. Return the response
    return AnalysisStartResponse(
        message="Analysis started successfully",
        analysis_id=analysis_id_str,
        status=AnalysisStatus.STARTED,
        estimated_duration="2-5 minutes",
    )


@router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse, responses={404: {"model": ErrorResponse}})
async def get_analysis_status_endpoint(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get the current status and progress of an analysis using its UUID.
    """
    logger.debug(f"Requesting status for analysis_id: {analysis_id}")
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        logger.warning(f"Invalid UUID format for analysis_id: {analysis_id}")
        raise HTTPException(status_code=400, detail="Invalid analysis ID format (must be UUID)")

    analysis: Optional[Analysis] = await analysis_service.get_analysis_status(session, analysis_id)

    if not analysis:
        logger.warning(f"Analysis ID not found in DB: {analysis_id}")
        raise HTTPException(status_code=404, detail="Analysis ID not found")

    logger.debug(f"Found analysis {analysis_id} with status: {analysis.status}")
    
    # Map DB model to Response model explicitly to handle id -> analysis_id mismatch
    return AnalysisStatusResponse(
        analysis_id=str(analysis.id),
        status=analysis.status,
        progress=analysis.progress,
        started_at=analysis.started_at,
        estimated_completion=None,
        completed_at=analysis.completed_at,
        results=AnalysisResults(**analysis.results) if analysis.results else None,
        report_paths=ReportPaths(**analysis.report_paths) if analysis.report_paths else None,
        error=analysis.error
    )


@router.get("/{analysis_id}/results", response_model=AnalysisStatusResponse, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def get_analysis_results_endpoint(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get the detailed results of a completed or failed analysis using its UUID.
    """
    logger.debug(f"Requesting results for analysis_id: {analysis_id}")
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        logger.warning(f"Invalid UUID format for analysis_id: {analysis_id}")
        raise HTTPException(status_code=400, detail="Invalid analysis ID format (must be UUID)")

    analysis: Optional[Analysis] = await analysis_service.get_analysis_results(session, analysis_id)

    if not analysis:
        status_check = await analysis_service.get_analysis_status(session, analysis_id)
        if status_check:
            logger.warning(f"Analysis {analysis_id} found but not yet completed (status: {status_check.status}).")
            raise HTTPException(status_code=409, detail=f"Analysis not completed yet (Status: {status_check.status.value})")
        else:
            logger.warning(f"Analysis ID not found for results query: {analysis_id}")
            raise HTTPException(status_code=404, detail="Analysis not found")

    logger.debug(f"Returning results for completed/failed analysis {analysis_id}")
    
    return AnalysisStatusResponse(
        analysis_id=str(analysis.id),
        status=analysis.status,
        progress=analysis.progress,
        started_at=analysis.started_at,
        estimated_completion=None,
        completed_at=analysis.completed_at,
        results=AnalysisResults(**analysis.results) if analysis.results else None,
        report_paths=ReportPaths(**analysis.report_paths) if analysis.report_paths else None,
        error=analysis.error
    )

@router.get("/", response_model=List[AnalysisStatusResponse])
async def list_analyses_endpoint(
    session: AsyncSession = Depends(get_session),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get a list of all analyses (most recent first).
    """
    logger.debug("Requesting list of all analyses")
    analyses: List[Analysis] = await analysis_service.list_analyses(session)
    logger.info(f"Returning {len(analyses)} analysis records.")
    
    return [
        AnalysisStatusResponse(
            analysis_id=str(a.id),
            status=a.status,
            progress=a.progress,
            started_at=a.started_at,
            estimated_completion=None,
            completed_at=a.completed_at,
            results=AnalysisResults(**a.results) if a.results else None,
            report_paths=ReportPaths(**a.report_paths) if a.report_paths else None,
            error=a.error
        ) for a in analyses
    ]