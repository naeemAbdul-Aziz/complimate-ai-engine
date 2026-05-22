# api/endpoints/regulations.py
"""
Regulation Management API Endpoints (V3)
========================================

Provides endpoints for managing regulation documents, including listing,
searching, rebuilding the index, and the V3 Admin API for uploading,
tracking, and retiring regulation PDFs with zero-downtime Pinecone updates.

Admin endpoints require the X-Admin-Key header matching the ADMIN_API_KEY env var.
"""

import hashlib
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import (
    APIRouter, BackgroundTasks, File, Form,
    Header, HTTPException, Query, UploadFile,
)
from pydantic import BaseModel

from api.services.analysis_service import AnalysisService
from config import settings
from utils import LoggerMixin

# --- Optional Celery integration ---
rebuild_index_task = None
if settings.ENABLE_CELERY:
    try:
        from tasks.regulation_tasks import rebuild_regulation_index as rebuild_index_task  # type: ignore
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class BaseResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


class RegulationInfo(BaseModel):
    """Metadata for a single indexed regulation."""
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
    total_regulations: int
    categories: Dict[str, int]
    storage_type: str
    last_updated: str
    regulations: List[RegulationInfo]


class RegulationRebuildResponse(BaseResponse):
    files_processed: int
    files_skipped: int
    files_failed: int
    total_regulations: int
    processed_files: List[Dict[str, Any]]
    error_files: List[Dict[str, Any]]


class RegulationCategoryResponse(BaseResponse):
    category: str
    count: int
    regulations: List[RegulationInfo]


# ---------------------------------------------------------------------------
# Router & service instance
# ---------------------------------------------------------------------------

router = APIRouter()


class RegulationEndpoints(LoggerMixin):
    def __init__(self):
        self.analysis_service = AnalysisService()


regulation_endpoints = RegulationEndpoints()


# ---------------------------------------------------------------------------
# Admin key guard
# ---------------------------------------------------------------------------

def _verify_admin_key(x_admin_key: Optional[str] = Header(default=None)) -> None:
    """Raises 401 if the X-Admin-Key header does not match ADMIN_API_KEY."""
    expected = settings.ADMIN_API_KEY
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin API is not configured. "
                "Set ADMIN_API_KEY in the environment to enable regulation management."
            ),
        )
    if x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key header.")


# ---------------------------------------------------------------------------
# Background tasks for V3 admin endpoints
# ---------------------------------------------------------------------------

async def _background_index_regulation(regulation_id: int) -> None:
    """OCR → chunk → Pinecone upsert for a single regulation PDF.

    Runs entirely outside the HTTP request lifecycle so the caller always
    receives a 202 regardless of OCR duration.
    """
    from api.db import AsyncSessionLocal
    from api.models.db_models import RegulationDocument

    async with AsyncSessionLocal() as session:
        reg = await session.get(RegulationDocument, regulation_id)
        if reg is None:
            return
        try:
            reg.status = "INDEXING"
            session.add(reg)
            await session.commit()

            manager = regulation_endpoints.analysis_service.regulation_manager
            file_path = Path(reg.storage_path)

            success = manager.index_regulation_file(file_path, reg.category)

            if success:
                meta = manager.regulations_metadata.get(reg.file_name)
                reg.chunk_count = meta.chunk_count if meta else 0
                reg.status = "ACTIVE"
                reg.indexed_at = datetime.datetime.utcnow()
                reg.pinecone_namespace = f"doc_{regulation_id}"
            else:
                reg.status = "ERROR"
                reg.error_message = "Indexing failed — check server logs for details."
        except Exception as exc:
            reg.status = "ERROR"
            reg.error_message = str(exc)[:500]

        session.add(reg)
        await session.commit()


async def _background_retire_regulation(
    regulation_id: int, pinecone_namespace: Optional[str]
) -> None:
    """Removes vectors from Pinecone for a retired regulation (best-effort)."""
    try:
        if (
            pinecone_namespace
            and settings.VECTOR_DB_PROVIDER == "pinecone"
            and settings.PINECONE_API_KEY
        ):
            from pinecone import Pinecone  # type: ignore

            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            index = pc.Index(settings.PINECONE_INDEX_NAME)
            index.delete(delete_all=True, namespace=pinecone_namespace)
    except Exception as exc:
        regulation_endpoints.logger.error(
            f"[retire] Failed to delete Pinecone vectors for regulation_id={regulation_id}: {exc}"
        )


# ---------------------------------------------------------------------------
# Read-only public endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=RegulationsListResponse)
async def list_regulations():
    """List all indexed regulations with metadata."""
    info = regulation_endpoints.analysis_service.regulation_manager.get_regulations_info()
    regulations = [RegulationInfo(**r) for r in info["regulations"]]
    return RegulationsListResponse(
        success=True,
        message=f"Retrieved {info['total_regulations']} regulations",
        total_regulations=info["total_regulations"],
        categories=info["categories"],
        storage_type=info["storage_type"],
        last_updated=info["last_updated"],
        regulations=regulations,
    )


@router.get("/categories", response_model=BaseResponse)
async def list_categories():
    """List all regulation categories with document counts."""
    info = regulation_endpoints.analysis_service.regulation_manager.get_regulations_info()
    return BaseResponse(
        success=True,
        message="Retrieved regulation categories",
        data={"categories": info["categories"], "total_categories": len(info["categories"])},
    )


@router.get("/category/{category}", response_model=RegulationCategoryResponse)
async def get_regulations_by_category(category: str):
    """Get all regulations in a specific category."""
    regulations_data = regulation_endpoints.analysis_service.get_regulations_by_category(category)  # type: ignore[attr-defined]
    regulations = [RegulationInfo(**r) for r in regulations_data]
    return RegulationCategoryResponse(
        success=True,
        message=f"Retrieved {len(regulations)} regulations in category '{category}'",
        category=category,
        count=len(regulations),
        regulations=regulations,
    )


@router.get("/status", response_model=BaseResponse)
async def get_regulation_status():
    """Get regulation system readiness and index statistics."""
    reg_manager = regulation_endpoints.analysis_service.regulation_manager
    info = reg_manager.get_regulations_info()
    is_ready = getattr(reg_manager, "is_ready", info.get("total_regulations", 0) > 0)
    return BaseResponse(
        success=True,
        message="Regulation system status retrieved",
        data={
            "is_ready": is_ready,
            "total_regulations": info["total_regulations"],
            "storage_type": info["storage_type"],
            "categories": info["categories"],
            "last_updated": info["last_updated"],
        },
    )


@router.get("/search", response_model=BaseResponse)
async def search_regulations(
    query: str = Query(..., description="Semantic search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
):
    """Semantic search across indexed regulation chunks."""
    results = regulation_endpoints.analysis_service.regulation_manager.search_regulations(
        query, category, limit
    )
    return BaseResponse(
        success=True,
        message=f"Returned {len(results)} search results",
        data={"query": query, "category": category, "limit": limit, "results": results},
    )


# ---------------------------------------------------------------------------
# Sync & async rebuild (admin — no key guard to preserve backward compat)
# ---------------------------------------------------------------------------

@router.post("/rebuild", response_model=RegulationRebuildResponse)
async def rebuild_regulations_index(
    force: bool = Query(False, description="Force rebuild even if files unchanged"),
):
    """Rebuild the regulation index synchronously (admin use only)."""
    regulation_endpoints.logger.info(f"Sync regulation index rebuild requested (force={force})")
    result = regulation_endpoints.analysis_service.rebuild_regulations_index(force=force)  # type: ignore[attr-defined]
    return RegulationRebuildResponse(
        success=True,
        message=f"Index rebuild completed: {result['files_processed']} files processed",
        files_processed=result["files_processed"],
        files_skipped=result["files_skipped"],
        files_failed=result["files_failed"],
        total_regulations=result["total_regulations"],
        processed_files=result["processed_files"],
        error_files=result["error_files"],
    )


@router.post("/rebuild/async", response_model=BaseResponse)
async def rebuild_regulations_index_async(
    force: bool = Query(False, description="Force rebuild even if files unchanged"),
):
    """Schedule an async regulation index rebuild via Celery. Returns a task_id."""
    if not settings.ENABLE_CELERY:
        raise HTTPException(status_code=400, detail="Celery is not enabled (ENABLE_CELERY=False).")
    if rebuild_index_task is None:
        raise HTTPException(status_code=500, detail="Regulation Celery task unavailable.")
    async_result = rebuild_index_task.apply_async(kwargs={"force": force}, queue="rag")
    return BaseResponse(
        success=True,
        message="Regulation index rebuild scheduled.",
        data={"task_id": async_result.id},
    )


# ---------------------------------------------------------------------------
# V3 Admin Regulation Management (require X-Admin-Key)
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=202)
async def upload_regulation(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Regulation PDF file"),
    title: str = Form(..., description="Human-readable title for this regulation"),
    category: str = Form(default="petroleum", description="petroleum | mining | environmental | labor | general"),
    description: str = Form(default="", description="Optional description"),
    x_admin_key: Optional[str] = Header(default=None),
):
    """[ADMIN] Upload a new regulation PDF.

    Saves the PDF locally, creates a DB tracking record, and dispatches a
    background task for OCR + Pinecone indexing. Returns 202 immediately.

    Poll GET /api/v1/regulations/doc/{id} to track indexing progress.

    **Requires header:** `X-Admin-Key: <ADMIN_API_KEY>`
    """
    _verify_admin_key(x_admin_key)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    file_size_mb = len(pdf_bytes) / (1024 * 1024)
    if file_size_mb > settings.MAX_REGULATION_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size ({file_size_mb:.1f} MB) exceeds the "
                f"{settings.MAX_REGULATION_FILE_SIZE_MB} MB limit."
            ),
        )

    file_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Lazy import to avoid circular imports at module load time
    from api.db import AsyncSessionLocal
    from api.models.db_models import RegulationDocument
    from sqlmodel import select

    async with AsyncSessionLocal() as session:
        # Duplicate check
        result = await session.execute(
            select(RegulationDocument).where(
                RegulationDocument.file_hash == file_hash,
                RegulationDocument.status == "ACTIVE",
            )
        )
        existing = result.first()
        if existing:
            dup = existing[0]
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A regulation with identical content is already ACTIVE "
                    f"(id={dup.id}, title='{dup.title}'). "
                    f"Call DELETE /api/v1/regulations/doc/{dup.id} first if replacing it."
                ),
            )

        # Save PDF to regulations directory
        dest_dir = settings.REGULATIONS_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = file.filename.replace(" ", "_")
        dest_path = dest_dir / safe_name
        dest_path.write_bytes(pdf_bytes)

        reg = RegulationDocument(
            file_name=safe_name,
            title=title,
            category=category,
            description=description or None,
            file_hash=file_hash,
            storage_path=str(dest_path),
            status="PENDING",
        )
        session.add(reg)
        await session.commit()
        await session.refresh(reg)
        regulation_id = reg.id

    background_tasks.add_task(_background_index_regulation, regulation_id)

    return {
        "regulation_id": regulation_id,
        "status": "INDEXING",
        "file_name": safe_name,
        "message": (
            f"PDF received and queued for Pinecone indexing. "
            f"Poll GET /api/v1/regulations/doc/{regulation_id} for progress."
        ),
    }


@router.get("/doc/{regulation_id}", response_model=BaseResponse)
async def get_regulation_doc_status(
    regulation_id: int,
    x_admin_key: Optional[str] = Header(default=None),
):
    """[ADMIN] Get indexing status of a single regulation document.

    Poll this after POST /upload returns 202 to track background OCR progress.

    **Requires header:** `X-Admin-Key: <ADMIN_API_KEY>`
    """
    _verify_admin_key(x_admin_key)

    from api.db import AsyncSessionLocal
    from api.models.db_models import RegulationDocument

    async with AsyncSessionLocal() as session:
        reg = await session.get(RegulationDocument, regulation_id)

    if reg is None:
        raise HTTPException(status_code=404, detail=f"Regulation document {regulation_id} not found.")

    return BaseResponse(
        success=True,
        message=f"Regulation {regulation_id} status retrieved.",
        data={
            "id": reg.id,
            "file_name": reg.file_name,
            "title": reg.title,
            "category": reg.category,
            "description": reg.description,
            "status": reg.status,
            "chunk_count": reg.chunk_count,
            "pinecone_namespace": reg.pinecone_namespace,
            "error_message": reg.error_message,
            "created_at": reg.created_at.isoformat() if reg.created_at else None,
            "indexed_at": reg.indexed_at.isoformat() if reg.indexed_at else None,
        },
    )


@router.delete("/doc/{regulation_id}", response_model=BaseResponse)
async def retire_regulation(
    regulation_id: int,
    background_tasks: BackgroundTasks,
    x_admin_key: Optional[str] = Header(default=None),
):
    """[ADMIN] Retire a regulation document.

    Marks the DB record as RETIRED and removes its Pinecone vectors
    asynchronously. In-flight analyses are not interrupted.

    **Requires header:** `X-Admin-Key: <ADMIN_API_KEY>`
    """
    _verify_admin_key(x_admin_key)

    from api.db import AsyncSessionLocal
    from api.models.db_models import RegulationDocument

    async with AsyncSessionLocal() as session:
        reg = await session.get(RegulationDocument, regulation_id)
        if reg is None:
            raise HTTPException(status_code=404, detail=f"Regulation {regulation_id} not found.")
        if reg.status == "RETIRED":
            raise HTTPException(status_code=409, detail=f"Regulation {regulation_id} is already RETIRED.")

        pinecone_namespace = reg.pinecone_namespace
        reg.status = "RETIRED"
        reg.retired_at = datetime.datetime.utcnow()
        session.add(reg)
        await session.commit()

    background_tasks.add_task(_background_retire_regulation, regulation_id, pinecone_namespace)

    return BaseResponse(
        success=True,
        message=(
            f"Regulation {regulation_id} has been retired. "
            "Pinecone vectors are being removed in the background."
        ),
    )