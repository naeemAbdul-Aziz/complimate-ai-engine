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
    AnalysisRequest, # Using this from context
    AnalysisStartResponse, # Using this from context
    AnalysisStatusResponse, # Using this for status AND results
    ErrorResponse, # Using this from context
    AnalysisStatus,
    # Assuming schemas.py might define these:
    # StartAnalysisRequest, # Simpler name? Using AnalysisRequest for now
    # StartAnalysisResponse,
    # AnalysisStatusModel, # Using AnalysisStatusResponse instead
    # AnalysisResultModel, # Not defined, using AnalysisStatusResponse
    # AnalysisResponseModel # Not defined, using AnalysisStatusResponse
)

# --- Service Imports ---
from api.services.analysis_service import AnalysisService
from api.services.file_service import FileService

# --- Logger ---
from config.logger import get_component_logger
logger = get_component_logger('api.endpoints.analysis')

# --- Router ---
router = APIRouter() # Prefix and tags are applied in api/main.py

# --- Dependency Injection for Services ---
# This approach maintains a singleton per worker process, which is generally okay
# but be mindful of state if services become complex.
# Consider FastAPI's standard dependency pattern if issues arise.

# --- ANALYSIS SERVICE DEPENDENCY ---
# Check if app state is used elsewhere, if not, simplify dependency
# The provided code has AnalysisService() instantiated directly. Let's use Depends for consistency.
_analysis_service_instance: Optional[AnalysisService] = None
def get_analysis_service() -> AnalysisService:
    """Dependency to get the singleton AnalysisService instance."""
    global _analysis_service_instance
    if _analysis_service_instance is None:
        logger.info("Initializing AnalysisService singleton...")
        _analysis_service_instance = AnalysisService()
    return _analysis_service_instance

# --- FILE SERVICE DEPENDENCY ---
# The upload endpoint provided uses a module-level singleton. Use Depends for consistency.
_file_service_instance: Optional[FileService] = None
def get_file_service() -> FileService:
    """Dependency to get the singleton FileService instance."""
    global _file_service_instance
    if _file_service_instance is None:
        logger.info("Initializing FileService singleton...")
        _file_service_instance = FileService()
    return _file_service_instance
# --- End Service Dependencies ---


# --- Endpoints ---

# NOTE: The provided analysis.py uses file_id, while the service uses file_path.
# Need to reconcile this. Assuming the endpoint gets the path from the file_id via FileService.

@router.post("/start", response_model=AnalysisStartResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
async def start_analysis_endpoint(
    request: AnalysisRequest, # Use schema from context
    session: AsyncSession = Depends(get_session), # Inject DB session
    analysis_service: AnalysisService = Depends(get_analysis_service),
    file_service: FileService = Depends(get_file_service) # Inject FileService
):
    """
    Start a new compliance analysis for a previously uploaded file using its file_id.
    """
    logger.info(f"Received request to start analysis for file_id: {request.file_id}")
    try:
        # 1. Get file path from file_id using FileService
        file_info = file_service.get_file_info(request.file_id) # Get full info
        if not file_info or not file_service.validate_file_exists(request.file_id):
            logger.warning(f"File ID not found or file missing on disk: {request.file_id}")
            raise HTTPException(status_code=404, detail=f"File ID '{request.file_id}' not found or file is missing.")

        file_path = file_info["file_path"]
        contract_name = file_info["original_filename"]

        # 2. Call the AnalysisService with the session and file path
        analysis_id_str = await analysis_service.start_analysis(
            session=session,
            file_path=file_path,
            contract_name=contract_name
        )
        logger.info(f"Analysis started with ID: {analysis_id_str} for file: {contract_name}")

        # 3. Return the response using the schema from context
        return AnalysisStartResponse(
            message="Analysis started successfully",
            analysis_id=analysis_id_str,
            status=AnalysisStatus.STARTED, # Use the enum value
            estimated_duration="2-5 minutes", # Hardcoded for now
            # started_at is handled by default_factory in the schema
        )
    except FileNotFoundError: # Should be caught by file_service check now
        logger.error(f"File not found unexpectedly for id: {request.file_id}")
        raise HTTPException(status_code=404, detail="File not found")
    except HTTPException as http_exc:
        # Re-raise known HTTP exceptions
        raise http_exc
    except Exception as e:
        logger.exception(f"Failed to start analysis for file_id {request.file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")


# Endpoint /start/upload seems redundant if /upload exists and returns file_id
# Let's keep the two status/results endpoints

@router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse, responses={404: {"model": ErrorResponse}})
async def get_analysis_status_endpoint(
    analysis_id: str,
    session: AsyncSession = Depends(get_session), # Inject DB session
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get the current status and progress of an analysis using its UUID.
    """
    logger.debug(f"Requesting status for analysis_id: {analysis_id}")
    try:
        # Validate UUID format before querying
        try:
            analysis_uuid = uuid.UUID(analysis_id)
        except ValueError:
            logger.warning(f"Invalid UUID format for analysis_id: {analysis_id}")
            raise HTTPException(status_code=400, detail="Invalid analysis ID format (must be UUID)")

        # Pass session to the service method
        analysis: Optional[Analysis] = await analysis_service.get_analysis_status(session, analysis_id)

        if not analysis:
            logger.warning(f"Analysis ID not found in DB: {analysis_id}")
            raise HTTPException(status_code=404, detail="Analysis ID not found")

        logger.debug(f"Found analysis {analysis_id} with status: {analysis.status}")
        # SQLModel object 'analysis' is compatible with Pydantic 'AnalysisStatusResponse'
        return analysis # FastAPI handles the conversion
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Error fetching status for analysis_id {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error retrieving status")


@router.get("/{analysis_id}/results", response_model=AnalysisStatusResponse, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
async def get_analysis_results_endpoint(
    analysis_id: str,
    session: AsyncSession = Depends(get_session), # Inject DB session
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get the detailed results of a completed or failed analysis using its UUID.
    """
    logger.debug(f"Requesting results for analysis_id: {analysis_id}")
    try:
         # Validate UUID format
        try:
            analysis_uuid = uuid.UUID(analysis_id)
        except ValueError:
            logger.warning(f"Invalid UUID format for analysis_id: {analysis_id}")
            raise HTTPException(status_code=400, detail="Invalid analysis ID format (must be UUID)")

        # Use the specific results method (which includes a status check)
        analysis: Optional[Analysis] = await analysis_service.get_analysis_results(session, analysis_id)

        if not analysis:
            # Check if it exists but is just not finished
            status_check = await analysis_service.get_analysis_status(session, analysis_id)
            if status_check:
                logger.warning(f"Analysis {analysis_id} found but not yet completed (status: {status_check.status}).")
                raise HTTPException(status_code=409, detail=f"Analysis not completed yet (Status: {status_check.status.value})")
            else:
                logger.warning(f"Analysis ID not found for results query: {analysis_id}")
                raise HTTPException(status_code=404, detail="Analysis not found")

        logger.debug(f"Returning results for completed/failed analysis {analysis_id}")
        return analysis # Return the full Analysis object (compatible with AnalysisStatusResponse)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Error fetching results for analysis_id {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error retrieving results")

# --- ADDED: List Analyses Endpoint ---
@router.get("/", response_model=List[AnalysisStatusResponse]) # Return a list of status models
async def list_analyses_endpoint(
    session: AsyncSession = Depends(get_session),
    analysis_service: AnalysisService = Depends(get_analysis_service)
):
    """
    Get a list of all analyses (most recent first).
    """
    logger.debug("Requesting list of all analyses")
    try:
        analyses: List[Analysis] = await analysis_service.list_analyses(session)
        logger.info(f"Returning {len(analyses)} analysis records.")
        # FastAPI will serialize the list of SQLModel objects correctly
        return analyses
    except Exception as e:
        logger.exception(f"Error listing analyses: {e}")
        raise HTTPException(status_code=500, detail="Internal server error listing analyses")
# --- END ADDED ---