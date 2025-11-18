"""Celery tasks for regulation indexing and management (P1/P2).

These tasks offload heavy vector index operations to the dedicated RAG
worker queue. They are intentionally thin wrappers around the existing
`RegulationManager` logic to preserve single responsibility.
"""
from __future__ import annotations

from typing import Optional
from tasks.celery_app import celery_app


@celery_app.task(name="regulations.rebuild_index")
def rebuild_regulation_index(force: bool = False) -> dict:
    from engine.regulation_manager import RegulationManager
    manager = RegulationManager()
    return manager.rebuild_index(force=force)


@celery_app.task(name="regulations.index_file")
def index_regulation_file(file_name: str, category: str = "general") -> dict:
    from pathlib import Path
    from engine.regulation_manager import RegulationManager
    from config import settings

    file_path = settings.REGULATIONS_DIR / file_name
    manager = RegulationManager()
    metadata = manager.index_regulation_file(file_path, category)
    return metadata.to_dict()


__all__ = ["rebuild_regulation_index", "index_regulation_file"]