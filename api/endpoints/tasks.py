"""Celery task status endpoints."""
from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
if settings.ENABLE_CELERY:
    try:
        from tasks.celery_app import celery_app
    except Exception:
        celery_app = None
else:
    celery_app = None


class TaskStatusResponse(BaseModel):
    success: bool
    message: str
    state: Optional[str] = None
    result: Optional[Any] = None
    task_id: Optional[str] = None


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    if not settings.ENABLE_CELERY:
        raise HTTPException(status_code=400, detail="Celery not enabled")
    if celery_app is None:
        raise HTTPException(status_code=500, detail="Celery app unavailable")
    try:
        async_result = celery_app.AsyncResult(task_id)
        state = async_result.state
        result = None
        if async_result.ready():
            try:
                result = async_result.get(timeout=0.5)
            except Exception:
                result = None
        return TaskStatusResponse(
            success=True,
            message="Task status retrieved",
            state=state,
            result=result,
            task_id=task_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {e}")


__all__ = ["router"]