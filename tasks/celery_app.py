# tasks/celery_app.py
"""
Celery application configuration for CompliMate AI Engine.

This is optional and only used when settings.ENABLE_CELERY is True.
"""
from __future__ import annotations

from celery import Celery
from config import settings

celery_app = Celery(
    "complimate_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Minimal, safe defaults
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_disable_rate_limits=False,
    broker_connection_retry_on_startup=True,
)

# Route heavy RAG tasks to dedicated queue (P1)
celery_app.conf.task_routes = {
    "regulations.*": {"queue": "rag"},
    "analysis.*": {"queue": "default"},
}

__all__ = ["celery_app"]
