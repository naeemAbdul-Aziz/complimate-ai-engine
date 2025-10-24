# api/endpoints/analysis.py
"""
API endpoints for managing and running compliance analyses.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File

# --- MODIFIED ---
from sqlmodel.ext.asyncio.session import AsyncSession
from api.db import get_session
from api.models.db_models import Analysis
# --- END MODIFIED ---

from api.models.schemas import (
    StartAnalysisRequest, 
    StartAnalysisResponse, 
    AnalysisStatusModel, 
    AnalysisResultModel,
    AnalysisResponseModel # This seems to be the one we want for results
)
from api.services.analysis_service import AnalysisService
from api.services.file_service import FileService

# --- Use dependency injection to get a singleton instance of services ---
# (This part of your design is good, we'll keep it)
def get_analysis_service() -> AnalysisService:
    """Get the singleton AnalysisService instance."""
    from api.main import app  # Lazy import to avoid circular dependency
    if "analysis_service" not in app.state:
        app.state.analysis_service = AnalysisService()
    return app.state.analysis_service

def get_file_service() -> FileService:
    """Get the singleton FileService instance."""
    from api.main import app
    if "file_service" not in app.state:
        app.state.file_service = FileService()
    return app.state.file_service
# --- End of dependency injection setup ---


router = APIRouter()

@router.post("/start", response_model=StartAnalysisResponse)
async def start_analysis_endpoint(
    request: StartAnalysisRequest,
    # --- MODIFIED ---
    session: AsyncSession = Depends(get_session),
    # --- END MODIFIED ---
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Start a new compliance analysis for a previously uploaded file.
    """
    try:
        # --- MODIFIED ---
        # Pass the session to the service method
        analysis_id = await analysis_service.start_analysis(
            session=session,
            file_path=request.file_path, 
            contract_name=request.contract_name
        )
        # --- END MODIFIED ---
        return StartAnalysisResponse(analysis_id=analysis_id, status="Analysis started")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found at the provided path")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")

@router.post("/start/upload", response_model=StartAnalysisResponse)
async def start_analysis_with_upload_endpoint(
    file: UploadFile = File(...),
    # --- MODIFIED ---
    session: AsyncSession = Depends(get_session),
    # --- END MODIFIED ---
    analysis_service: AnalysisService = Depends(get_analysis_service),
    file_service: FileService = Depends(get_file_service)
):
    """
    Upload a file and immediately start a compliance analysis.
    """
    try:
        # Save the file first
        saved_path = await file_service.save_upload_file(file)
        
        # --- MODIFIED ---
        # Pass the session to the service method
        analysis_id = await analysis_service.start_analysis(
            session=session,
            file_path=str(saved_path), 
            contract_name=file.filename or f"analysis_{saved_path.stem}"
        )
        # --- END MODIFIED ---
        return StartAnalysisResponse(analysis_id=analysis_id, status="Analysis started")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload and start analysis: {str(e)}")

@router.get("/{analysis_id}/status", response_model=AnalysisStatusModel)
async def get_analysis_status_endpoint(
    analysis_id: str,
    # --- MODIFIED ---
    session: AsyncSession = Depends(get_session),
    # --- END MODIFIED ---
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get the current status and progress of an analysis.
    """
    # --- MODIFIED ---
    # Pass the session and get the DB model back
    analysis = await analysis_service.get_analysis_status(session, analysis_id)
    # --- END MODIFIED ---
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis ID not found")
    
    # SQLModel objects are compatible with Pydantic, so this works
    return analysis

@router.get("/{analysis_id}/results", response_model=AnalysisResponseModel)
async def get_analysis_results_endpoint(
    analysis_id: str,
    # --- MODIFIED ---
    session: AsyncSession = Depends(get_session),
    # --- END MODIFIED ---
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get the detailed results of a completed analysis.
    """
    # --- MODIFIED ---
    analysis = await analysis_service.get_analysis_results(session, analysis_id)
    # --- END MODIFIED ---
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found or not completed")
    
    # The AnalysisResponseModel expects the dictionary-like structure
    # which the SQLModel object provides.
    return analysis

@router.get("/", response_model=List[AnalysisStatusModel])
async def list_analyses_endpoint(
    # --- MODIFIED ---
    session: AsyncSession = Depends(get_session),
    # --- END MODIFIED ---
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get a list of all recent analyses.
    """
    # --- MODIFIED ---
    analyses = await analysis_service.list_analyses(session)
    return analyses
    # --- END MODIFIED ---