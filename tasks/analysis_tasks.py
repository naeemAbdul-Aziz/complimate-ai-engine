# tasks/analysis_tasks.py
"""
Celery tasks for contract analysis.

These tasks are thin wrappers that call existing async analysis workflows.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from tasks.celery_app import celery_app
from api.services.analysis_service import AnalysisService


@celery_app.task(name="analysis.run", bind=True)
def run_analysis_task(self, analysis_id: str) -> dict:
    """Run the analysis for a given analysis_id using the existing service."""
    # Initialize the service (sets up models/index lazily)
    service = AnalysisService()

    # Execute the async method in a fresh event loop
    try:
        asyncio.run(service._run_analysis(analysis_id))
        return {"status": "scheduled", "analysis_id": analysis_id}
    except Exception as exc:
        # Return error info; Celery will record FAILURE state automatically
        return {"status": "error", "error": str(exc), "analysis_id": analysis_id}
