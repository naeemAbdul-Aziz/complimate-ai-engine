# api/endpoints/upload.py
"""Upload endpoints for contract files."""
from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, HTTPException
from api.models.schemas import ContractUploadResponse, ErrorResponse
from api.services.file_service import FileService

router = APIRouter(prefix="", tags=["upload"])

# Module-level singleton service (in-memory registry per process)
file_service = FileService()


@router.post(
    "/upload",
    response_model=ContractUploadResponse,
    responses={400: {"model": ErrorResponse}},
)
async def upload_contract(file: UploadFile = File(...)) -> ContractUploadResponse:
    """Upload a contract file for analysis."""
    try:
        result = await file_service.upload_file(file)
        return ContractUploadResponse(
            message=result["message"],
            filename=result["filename"],
            file_id=result["file_id"],
            file_path=result["file_path"],
            file_size=result.get("file_size"),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def get_file_service() -> FileService:
    """Accessor for shared FileService instance (used by other routers)."""
    return file_service
