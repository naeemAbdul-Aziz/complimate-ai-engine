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


router = APIRouter(prefix="/regulations", tags=["regulations"])


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
    try:
        info = regulation_endpoints.analysis_service.get_regulations_info()
        
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
        
    except Exception as e:
        regulation_endpoints.logger.error(f"Failed to list regulations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve regulations: {str(e)}")


@router.get("/categories", response_model=BaseResponse)
async def list_categories():
    """
    Get available regulation categories.
    
    Returns a summary of all regulation categories and their counts.
    """
    try:
        info = regulation_endpoints.analysis_service.get_regulations_info()
        
        return BaseResponse(
            success=True,
            message="Retrieved regulation categories",
            data={
                "categories": info["categories"],
                "total_categories": len(info["categories"])
            }
        )
        
    except Exception as e:
        regulation_endpoints.logger.error(f"Failed to get categories: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve categories: {str(e)}")


@router.get("/category/{category}", response_model=RegulationCategoryResponse)
async def get_regulations_by_category(category: str):
    """
    Get all regulations in a specific category.
    
    Args:
        category: The regulation category (petroleum, mining, environmental, labor, general)
    """
    try:
        regulations_data = regulation_endpoints.analysis_service.get_regulations_by_category(category)
        
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
        
    except Exception as e:
        regulation_endpoints.logger.error(f"Failed to get regulations for category {category}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to retrieve regulations for category '{category}': {str(e)}"
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
    try:
        regulation_endpoints.logger.info(f"Starting regulation index rebuild (force={force})")
        
        result = regulation_endpoints.analysis_service.rebuild_regulations_index(force=force)
        
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
        
    except Exception as e:
        regulation_endpoints.logger.error(f"Failed to rebuild index: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to rebuild regulation index: {str(e)}")


@router.get("/status", response_model=BaseResponse)
async def get_regulation_status():
    """
    Get the current status of the regulation system.
    
    Returns information about the regulation index, storage type,
    and readiness status.
    """
    try:
        is_ready = regulation_endpoints.analysis_service.is_ready
        info = regulation_endpoints.analysis_service.get_regulations_info()
        
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
        
    except Exception as e:
        regulation_endpoints.logger.error(f"Failed to get regulation status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get regulation status: {str(e)}")


@router.get("/search", response_model=BaseResponse)
async def search_regulations(
    query: str = Query(..., description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results")
):
    """
    Search through regulation content.
    
    Performs semantic search across all indexed regulations to find
    relevant content matching the query.
    
    Args:
        query: The search query
        category: Optional category filter
        limit: Maximum number of results to return
    """
    try:
        # This would require implementing search functionality in the regulation manager
        # For now, return a placeholder response
        
        regulation_endpoints.logger.info(f"Regulation search requested: '{query}' in category '{category}'")
        
        return BaseResponse(
            success=True,
            message="Search functionality coming soon",
            data={
                "query": query,
                "category": category,
                "limit": limit,
                "note": "Advanced regulation search is planned for the next release"
            }
        )
        
    except Exception as e:
        regulation_endpoints.logger.error(f"Failed to search regulations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search regulations: {str(e)}")