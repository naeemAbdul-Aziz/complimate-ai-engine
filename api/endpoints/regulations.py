# api/endpoints/regulations.py
"""
Regulation Management API Endpoints
=================================

This module contains API endpoints for managing regulation documents,
including indexing, querying, and metadata management.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services.analysis_service import AnalysisService
from config import settings
if settings.ENABLE_CELERY:
    try:
        from tasks.regulation_tasks import rebuild_regulation_index as rebuild_index_task
    except Exception:
        rebuild_index_task = None
# Define BaseResponse here if not available in api.models.schemas
class BaseResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
from utils import LoggerMixin


class RegulationInfo(BaseModel):
    """Information about a regulation document."""
    file_name: str
    category: str
    title: str
    effective_date: Optional[str] = None
    last_amended: Optional[str] = None
    file_size: int
    chunk_count: int
    description: str
    tags: List[str]
    indexed_date: str


class RegulationsListResponse(BaseResponse):
    """Response for regulations list endpoint."""
    total_regulations: int
    categories: Dict[str, int]
    storage_type: str
    last_updated: str
    regulations: List[RegulationInfo]


class RegulationRebuildResponse(BaseResponse):
    """Response for regulation index rebuild."""
    files_processed: int
    files_skipped: int
    files_failed: int
    total_regulations: int
    processed_files: List[Dict[str, Any]]
    error_files: List[Dict[str, Any]]


class RegulationCategoryResponse(BaseResponse):
    """Response for regulations by category."""
    category: str
    count: int
    regulations: List[RegulationInfo]


# Router prefix is applied in api/main.py to avoid double-prefixing
router = APIRouter()


class RegulationEndpoints(LoggerMixin):
    """Regulation management endpoints."""
    
    def __init__(self):
        self.analysis_service = AnalysisService()


# Create endpoints instance
regulation_endpoints = RegulationEndpoints()


@router.get("/", response_model=RegulationsListResponse)
async def list_regulations():
    """
    Get information about all indexed regulations.
    
    Returns comprehensive information about all regulation documents
    including metadata, categories, and indexing status.
    """
    info = regulation_endpoints.analysis_service.regulation_manager.get_regulations_info()
    
    regulations = [
        RegulationInfo(**reg_data) for reg_data in info["regulations"]
    ]
    
    return RegulationsListResponse(
        success=True,
        message=f"Retrieved {info['total_regulations']} regulations",
        total_regulations=info["total_regulations"],
        categories=info["categories"],
        storage_type=info["storage_type"],
        last_updated=info["last_updated"],
        regulations=regulations
    )


@router.get("/categories", response_model=BaseResponse)
async def list_categories():
    """
    Get available regulation categories.
    
    Returns a summary of all regulation categories and their counts.
    """
    info = regulation_endpoints.analysis_service.regulation_manager.get_regulations_info()
    
    return BaseResponse(
        success=True,
        message="Retrieved regulation categories",
        data={
            "categories": info["categories"],
            "total_categories": len(info["categories"])
        }
    )


@router.get("/category/{category}", response_model=RegulationCategoryResponse)
async def get_regulations_by_category(category: str):
    """
    Get all regulations in a specific category.
    
    Args:
        category: The regulation category (petroleum, mining, environmental, labor, general)
    """
    regulations_data = regulation_endpoints.analysis_service.get_regulations_by_category(category)  # type: ignore[attr-defined]
    
    regulations = [
        RegulationInfo(**reg_data) for reg_data in regulations_data
    ]
    
    return RegulationCategoryResponse(
        success=True,
        message=f"Retrieved {len(regulations)} regulations in category '{category}'",
        category=category,
        count=len(regulations),
        regulations=regulations
    )


@router.post("/rebuild", response_model=RegulationRebuildResponse)
async def rebuild_regulations_index(force: bool = Query(False, description="Force rebuild even if files haven't changed")):
    """
    Rebuild the regulation index.
    
    Scans the regulations directory for new or modified files and rebuilds
    the vector index. Use force=true to rebuild all files regardless of changes.
    
    Args:
        force: Whether to force rebuild of all files
    """
    regulation_endpoints.logger.info(f"Starting regulation index rebuild (force={force})")
    
    result = regulation_endpoints.analysis_service.rebuild_regulations_index(force=force)  # type: ignore[attr-defined]
    
    return RegulationRebuildResponse(
        success=True,
        message=f"Index rebuild completed: {result['files_processed']} files processed",
        files_processed=result["files_processed"],
        files_skipped=result["files_skipped"],
        files_failed=result["files_failed"],
        total_regulations=result["total_regulations"],
        processed_files=result["processed_files"],
        error_files=result["error_files"]
    )


@router.post("/rebuild/async", response_model=BaseResponse)
async def rebuild_regulations_index_async(force: bool = Query(False, description="Force rebuild even if files haven't changed")):
    """Schedule an asynchronous regulation index rebuild via Celery (P1).

    Returns a task id which can be polled via the generic Celery result backend.
    """
    if not settings.ENABLE_CELERY:
        raise HTTPException(status_code=400, detail="Celery is not enabled")
    if rebuild_index_task is None:
        raise HTTPException(status_code=500, detail="Regulation Celery task not available")

    async_result = rebuild_index_task.apply_async(kwargs={"force": force}, queue="rag")
    return BaseResponse(success=True, message="Regulation index rebuild scheduled", data={"task_id": async_result.id})


@router.get("/status", response_model=BaseResponse)
async def get_regulation_status():
    """
    Get the current status of the regulation system.
    
    Returns information about the regulation index, storage type,
    and readiness status.
    """
    reg_manager = regulation_endpoints.analysis_service.regulation_manager
    info = reg_manager.get_regulations_info()
    # Fallback readiness: use manager.is_ready if present, else check if any regulations are indexed.
    is_ready = getattr(reg_manager, "is_ready", info.get("total_regulations", 0) > 0)
    
    return BaseResponse(
        success=True,
        message="Regulation system status retrieved",
        data={
            "is_ready": is_ready,
            "total_regulations": info["total_regulations"],
            "storage_type": info["storage_type"],
            "categories": info["categories"],
            "last_updated": info["last_updated"]
        }
    )


@router.get("/search", response_model=BaseResponse)
async def search_regulations(
    query: str = Query(..., description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results")
):
    """Semantic search across indexed regulation chunks."""
    results = regulation_endpoints.analysis_service.regulation_manager.search_regulations(query, category, limit)  # type: ignore
    return BaseResponse(
        success=True,
        message=f"Returned {len(results)} search results",
        data={
            "query": query,
            "category": category,
            "limit": limit,
            "results": results,
        }
    )