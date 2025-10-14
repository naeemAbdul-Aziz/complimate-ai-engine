# api/endpoints/analysis.py
"""Analysis endpoints for starting and monitoring contract analyses."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from api.models.schemas import (
    AnalysisRequest,
    AnalysisStartResponse,
    AnalysisStatusResponse,
    ErrorResponse,
    AnalysisStatus,
)
from api.services.analysis_service import AnalysisService
from api.endpoints.upload import get_file_service

router = APIRouter(prefix="/analysis", tags=["analysis"])

analysis_service = AnalysisService()


@router.post("/start", response_model=AnalysisStartResponse, responses={400: {"model": ErrorResponse}})
async def start_analysis(request: AnalysisRequest) -> AnalysisStartResponse:
    """Start a new analysis for a previously uploaded file."""
    file_svc = get_file_service()
    file_info = file_svc.get_file_info(request.file_id)
    if not file_info:
        raise HTTPException(status_code=400, detail="Invalid or unknown file_id. Upload the file first.")
    file_path = file_svc.get_file_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=400, detail="File no longer exists on server.")

    analysis_id = await analysis_service.start_analysis(file_path, file_info["original_filename"])

    return AnalysisStartResponse(
        message="Analysis started successfully",
        analysis_id=analysis_id,
        status=AnalysisStatus.STARTED,
        estimated_duration="2-5 minutes",
    )


@router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse)
async def get_status(analysis_id: str) -> AnalysisStatusResponse:
    """Get the current status for an analysis."""
    status = analysis_service.get_analysis_status(analysis_id)
    if not status:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return AnalysisStatusResponse(
        analysis_id=status["id"],
        status=status["status"],
        progress=status["progress"],
        started_at=status["started_at"],
        estimated_completion=status.get("estimated_completion"),
        completed_at=status.get("completed_at"),
        results=status.get("results"),
        report_paths=status.get("report_paths"),
        error=status.get("error"),
    )


@router.get("/{analysis_id}/results", response_model=AnalysisStatusResponse)
async def get_results(analysis_id: str) -> AnalysisStatusResponse:
    """Get final results and report links for a completed analysis."""
    status = analysis_service.get_analysis_status(analysis_id)
    if not status:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if status["status"] not in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED, AnalysisStatus.ERROR):
        raise HTTPException(status_code=409, detail="Analysis not completed yet")

    return AnalysisStatusResponse(
        analysis_id=status["id"],
        status=status["status"],
        progress=status["progress"],
        started_at=status["started_at"],
        estimated_completion=status.get("estimated_completion"),
        completed_at=status.get("completed_at"),
        results=status.get("results"),
        report_paths=status.get("report_paths"),
        error=status.get("error"),
    )
