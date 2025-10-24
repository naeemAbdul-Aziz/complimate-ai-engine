# api/services/analysis_service.py
"""
Analysis service for CompliMate AI Engine
========================================

This module contains the business logic for contract compliance analysis.
"""

import asyncio
import uuid  # --- MODIFIED: Added uuid import ---
import datetime
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# --- MODIFIED: Added SQLModel imports ---
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
# --- END MODIFIED ---

from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.base.llms.types import CompletionResponse
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding

from engine.parsing import parse_contract
from engine.retrieval import find_relevant_regulations
from engine.violation import create_violation_prompt, process_batch_violation_responses
from engine.regulation_manager import RegulationManager
from reporting.report_generator import generate_report, generate_text_report, generate_pdf_report

from config import settings
from config.logger import get_component_logger, log_performance
from utils import LoggerMixin, log_performance
from utils.circuit_breaker import SimpleCircuitBreaker
from api.models.schemas import AnalysisStatus, ViolationModel
# --- MODIFIED: Import the DB model ---
from api.models.db_models import Analysis
# --- END MODIFIED ---
from config import settings

# Optional import for WebSocket broadcasting (decoupled)
try:
    from api.realtime import manager as ws_manager
    from api.models.schemas import WebSocketEvent
except Exception:  # pragma: no cover - if ws module not loaded
    ws_manager = None
    WebSocketEvent = None


class AnalysisService(LoggerMixin):
    """Service class for handling contract compliance analysis."""
    
    def __init__(self):
        # Use enhanced component logger instead of LoggerMixin
        self._component_logger = get_component_logger('analysis_service')
        self.regulation_manager = RegulationManager()
        # --- MODIFIED: Removed in-memory dictionary ---
        # self.active_analyses: Dict[str, Dict[str, Any]] = {} 
        # --- END MODIFIED ---
        self._initialize_models()
        # Initialize Circuit Breaker using settings
        self.openai_breaker = SimpleCircuitBreaker(
            fail_threshold=settings.CIRCUIT_BREAKER_FAIL_THRESHOLD,
            reset_seconds=settings.CIRCUIT_BREAKER_RESET_SECONDS
        )
    
    @property
    def logger(self):
        """Get the component logger."""
        return self._component_logger
    
    def _initialize_models(self) -> None:
        """Initialize OpenAI models and regulation index."""
        try:
            self.logger.info("Initializing OpenAI models and regulation index...")
            
            # Initialize OpenAI models
            Settings.llm = OpenAI(
                model=settings.OPENAI_MODEL,
                api_key=settings.OPENAI_API_KEY,
                request_timeout=settings.OPENAI_REQUEST_TIMEOUT,
                max_retries=settings.OPENAI_MAX_RETRIES,
            )
            Settings.embed_model = OpenAIEmbedding(
                model=settings.OPENAI_EMBEDDING_MODEL,
                api_key=settings.OPENAI_API_KEY,
                max_retries=settings.OPENAI_MAX_RETRIES,
            )
            
            # Initialize regulation manager and get index
            regulation_index = self.regulation_manager.get_regulation_index()
            if regulation_index is None:
                self.logger.warning("No regulation index available. Please rebuild regulations through the API.")
            else:
                self.logger.info("Regulation index loaded successfully")
            
            self.logger.info("Models initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize models: {e}")
            raise
    
    # --- MODIFIED: Refactored to use database session ---
    @log_performance
    async def start_analysis(self, session: AsyncSession, file_path: str, contract_name: str) -> str:
        """
        Start a new contract analysis by creating a record in the database.
        
        Args:
            session: The database session.
            file_path: Path to the contract file.
            contract_name: Name of the contract file.
            
        Returns:
            Analysis ID (as a string).
        """
        
        # Create a new Analysis DB record
        new_analysis = Analysis(
            contract_name=contract_name,
            file_path=file_path,
            status=AnalysisStatus.STARTED,
            progress="Analysis started"
        )
        
        # Add to session and commit
        session.add(new_analysis)
        await session.commit()
        await session.refresh(new_analysis)
        
        analysis_id_str = str(new_analysis.id)
        
        # Start analysis in background, passing the ID
        asyncio.create_task(self._run_analysis(analysis_id_str))
        
        self.logger.info(f"Started analysis {analysis_id_str} for contract {contract_name}")
        return analysis_id_str
    # --- END MODIFIED ---
    
    async def _execute_prompt_with_semaphore(
        self, 
        prompt: str, 
        semaphore: asyncio.Semaphore
    ) -> CompletionResponse:
        """Executes a single LLM prompt call, respecting semaphore and circuit breaker."""
        async with semaphore:
            if self.openai_breaker.is_open():
                self.logger.warning("OpenAI circuit breaker is open. Skipping request.")
                raise Exception("OpenAI circuit breaker is open")

            try:
                response = await Settings.llm.acomplete(prompt)
                self.openai_breaker.record_success()
                return response
            except Exception as e:
                error_str = str(e).lower()
                error_type = type(e).__name__
                
                if "429" in error_str or "ratelimiterror" in error_type.lower():
                    self.logger.warning(f"OpenAI Rate Limit encountered: {e}")
                    self.openai_breaker.record_failure()
                elif "500" in error_str or "internalservererror" in error_type.lower() or \
                     "502" in error_str or "badgateway" in error_type.lower() or \
                     "503" in error_str or "serviceunavailable" in error_type.lower():
                    self.logger.error(f"OpenAI Server Error encountered: {e}")
                    self.openai_breaker.record_failure()
                
                raise e

    # --- MODIFIED: Major refactor for background processing with DB ---
    async def _run_analysis(self, analysis_id_str: str) -> None:
        """
        Run the actual analysis in the background.
        
        This function runs in a separate task and MUST create its own
        database session.
        
        Args:
            analysis_id_str: ID of the analysis to run (as a string).
        """
        
        # Import here to avoid circular dependency at module level
        from api.db import AsyncSessionLocal
        
        analysis_id = uuid.UUID(analysis_id_str)
        analysis: Optional[Analysis] = None # Define analysis in outer scope

        # Create a new session scope for this background task
        async with AsyncSessionLocal() as session:
            try:
                # Get the analysis object from the DB
                analysis = await session.get(Analysis, analysis_id)
                if not analysis:
                    self.logger.error(f"Analysis {analysis_id} not found in DB for background run.")
                    return

                # Update status in DB
                analysis.status = AnalysisStatus.RUNNING
                analysis.progress = "Parsing contract document..."
                await session.commit() 
                
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "parse",
                    "detail": "Parsing contract document"
                })
                
                # Parse contract
                contract_nodes = parse_contract(analysis.file_path)
                if not contract_nodes:
                    raise ValueError("No content could be extracted from the contract")
                
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "chunk",
                    "detail": "Extracted contract sections",
                    "current": len(contract_nodes)
                })
                
                # Generate prompts and tasks
                analysis.progress = f"Generating analysis prompts for {len(contract_nodes)} sections..."
                await session.commit()
                
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "prompt_gen",
                    "detail": "Generating prompts",
                    "total": len(contract_nodes)
                })
                
                tasks = []
                prompt_metadata_list = []

                concurrency_limit = settings.OPENAI_CONCURRENCY_LIMIT
                semaphore = asyncio.Semaphore(concurrency_limit)
                self.logger.info(f"Using semaphore to limit LLM concurrency to {concurrency_limit} tasks.")
                
                for node in contract_nodes:
                    contract_content = node.get_content()
                    if not contract_content or contract_content.isspace():
                        continue
                    
                    relevant_regs = find_relevant_regulations(
                        node, 
                        self.regulation_manager.get_regulation_index(), 
                        top_n=settings.HYBRID_SEARCH_TOP_K
                    )
                    
                    if not relevant_regs:
                        continue
                    
                    for reg_result in relevant_regs:
                        reg_node = reg_result.node
                        reg_content = reg_node.get_content()
                        reg_metadata = reg_node.metadata or {}
                        
                        if not reg_content or reg_content.isspace():
                            continue
                        
                        prompt = create_violation_prompt(contract_content, reg_content, reg_metadata)
                        tasks.append(self._execute_prompt_with_semaphore(prompt, semaphore))

                        prompt_metadata_list.append({
                            "contract_node_id": node.node_id,
                            "regulation_node_id": reg_node.node_id,
                            "contract_clause_snippet": contract_content[:300] + "...",
                            "regulation_excerpt_snippet": reg_content[:300] + "...",
                        })
                
                if not tasks:
                    analysis.progress = "No analysis needed - contract appears compliant"
                    analysis.status = AnalysisStatus.COMPLETED
                    analysis.completed_at = datetime.datetime.now()
                    await session.commit()
                    
                    await self._broadcast_ws(analysis_id_str, "complete", {
                        "violations": 0,
                        "duration_seconds": (analysis.completed_at - analysis.started_at).total_seconds()
                    })
                    return
                
                # Execute LLM analysis
                analysis.progress = f"Processing {len(tasks)} compliance checks with AI..."
                await session.commit()
                
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "llm",
                    "detail": "Submitting compliance checks",
                    "total": len(tasks)
                })
                
                batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
                
                typed_batch_responses = []
                breaker_failures = 0
                other_failures = 0
                
                for resp in batch_responses:
                    if isinstance(resp, Exception):
                        if "OpenAI circuit breaker is open" in str(resp):
                            breaker_failures += 1
                        else:
                            other_failures += 1
                        typed_batch_responses.append(resp)
                    elif isinstance(resp, CompletionResponse):
                        typed_batch_responses.append(resp)
                    else:
                        other_failures += 1
                        typed_batch_responses.append(Exception(f"Unknown response type: {type(resp)}"))

                if breaker_failures > 0:
                    self.logger.warning(f"{breaker_failures}/{len(tasks)} tasks skipped due to open circuit breaker.")
                if other_failures > 0:
                    self.logger.warning(f"{other_failures}/{len(tasks)} tasks failed with other errors.")
                
                all_violations = process_batch_violation_responses(typed_batch_responses, prompt_metadata_list)
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "violations",
                    "detail": "Aggregated potential violations",
                    "current": len(all_violations)
                })
                
                # Generate reports
                analysis.progress = "Generating compliance reports..."
                await session.commit()
                
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "reporting",
                    "detail": "Generating reports"
                })
                
                report_data = self._create_report_data(
                    analysis.contract_name,
                    analysis.file_path,
                    all_violations,
                    len(tasks),
                    typed_batch_responses
                )
                
                report_paths = await self._generate_reports(analysis_id_str, report_data)
                
                # Update analysis with final results
                analysis.status = AnalysisStatus.COMPLETED
                analysis.completed_at = datetime.datetime.now()
                analysis.progress = "Analysis completed successfully"
                analysis.results = self._create_analysis_summary(all_violations, analysis)
                analysis.report_paths = report_paths
                await session.commit()
                
                await self._broadcast_ws(analysis_id_str, "complete", {
                    "violations": len(all_violations),
                    "duration_seconds": (analysis.completed_at - analysis.started_at).total_seconds()
                })
                
                self.logger.info(f"Analysis {analysis_id} completed successfully")
                
            except Exception as e:
                self.logger.error(f"Analysis {analysis_id} failed: {e}")
                
                # Try to update the DB record with the error
                if analysis: # Check if analysis object was fetched
                    analysis.status = AnalysisStatus.ERROR
                    analysis.completed_at = datetime.datetime.now()
                    
                    if "OpenAI circuit breaker is open" in str(e):
                        analysis.progress = "Analysis failed due to API errors"
                        analysis.error = "Analysis failed due to sustained OpenAI API issues (Circuit Breaker Open)."
                        await self._broadcast_ws(analysis_id_str, "error", {
                            "message": analysis.error, "retryable": False
                        })
                    else:
                        analysis.progress = "Analysis failed"
                        analysis.error = str(e)
                        await self._broadcast_ws(analysis_id_str, "error", {
                            "message": str(e), "retryable": True
                        })
                    
                    await session.commit() # Commit the error state
                else:
                    # This should not happen if start_analysis worked
                    self.logger.error(f"Analysis {analysis_id} failed, but analysis object was not found to record error.")

    # --- END MODIFIED ---

    async def _broadcast_ws(self, analysis_id: str, event_type: str, payload: dict) -> None:
        """Helper to broadcast a WebSocket event if enabled and manager is available."""
        # This method needs no changes, as it just uses the analysis_id string
        try:
            if not settings.ENABLE_WEBSOCKETS:
                return
            if ws_manager is None or WebSocketEvent is None:
                return
            evt = WebSocketEvent(type=event_type, analysis_id=analysis_id, payload=payload, schema_version=1)
            if event_type == "progress" and hasattr(ws_manager, "broadcast_throttled"):
                await ws_manager.broadcast_throttled(analysis_id, evt)
            else:
                await ws_manager.broadcast(analysis_id, evt)
        except Exception:
            pass
    
    def _create_report_data(
        self, 
        contract_name: str, 
        file_path: str, 
        violations: List[dict], 
        total_prompts: int, 
        batch_responses: List
    ) -> dict:
        """Create report data structure."""
        successful_responses = sum(1 for r in batch_responses if isinstance(r, CompletionResponse))
        failed_responses = sum(1 for r in batch_responses if isinstance(r, Exception))
        
        return {
            "contract_name": contract_name,
            "contract_path": file_path,
            "regulation_file": str(settings.REGULATION_FILE),
            "analysis_timestamp": datetime.datetime.now().isoformat(),
            "total_prompts_sent": total_prompts,
            "successful_responses": successful_responses,
            "failed_responses": failed_responses,
            "potential_issues_found": len(violations),
            "violations": violations,
        }
    
    async def _generate_reports(self, analysis_id: str, report_data: dict) -> dict:
        """Generate all report formats."""
        base_name = f"{report_data['contract_name']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        report_paths = {
            "json_file": settings.REPORTS_DIR / f"{base_name}_report.json",
            "txt": settings.REPORTS_DIR / f"{base_name}_report.txt",
            "pdf": settings.REPORTS_DIR / f"{base_name}_report.pdf"
        }
        
        generate_report(report_data, str(report_paths["json_file"]))
        generate_text_report(report_data, str(report_paths["txt"]))
        generate_pdf_report(report_data, str(report_paths["pdf"]))
        
        def to_url(p: Path) -> str:
            return f"/reports/{p.name}"
        return {k: to_url(v) for k, v in report_paths.items()}
    
    def _create_analysis_summary(self, violations: List[dict], analysis: Analysis) -> dict:
        """Create analysis results summary."""
        severity_counts = {"High": 0, "Medium": 0, "Low": 0}
        
        for violation in violations:
            severity = violation.get("severity", "Medium")
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        duration = None
        if analysis.completed_at and analysis.started_at:
            duration_seconds = (analysis.completed_at - analysis.started_at).total_seconds()
            duration = f"{duration_seconds / 60:.1f} minutes"
        
        return {
            "total_violations": len(violations),
            "high_severity": severity_counts["High"],
            "medium_severity": severity_counts["Medium"],
            "low_severity": severity_counts["Low"],
            "analysis_duration": duration or "Unknown"
        }
    
    # --- MODIFIED: Refactored to use database session ---
    async def get_analysis_status(self, session: AsyncSession, analysis_id: str) -> Optional[Analysis]:
        """Get the current status of an analysis from the DB."""
        try:
            analysis_uuid = uuid.UUID(analysis_id)
            analysis = await session.get(Analysis, analysis_uuid)
            return analysis
        except ValueError: # Invalid UUID format
            return None
    
    async def get_analysis_results(self, session: AsyncSession, analysis_id: str) -> Optional[Analysis]:
        """Get detailed results of a completed analysis from the DB."""
        try:
            analysis_uuid = uuid.UUID(analysis_id)
            analysis = await session.get(Analysis, analysis_uuid)
            
            if not analysis or analysis.status != AnalysisStatus.COMPLETED:
                return None
            
            return analysis
        except ValueError:
            return None
    
    async def list_analyses(self, session: AsyncSession) -> List[Analysis]:
        """Get list of all analyses from the DB."""
        statement = select(Analysis).order_by(Analysis.started_at.desc())
        results = await session.exec(statement)
        return results.all()
    # --- END MODIFIED ---
    
    # --- MODIFIED: Removed cleanup_old_analyses method ---
    # The database now keeps a permanent record.
    # We would write a separate script for archival or deletion if needed.
    # --- END MODIFIED ---
    
    @property
    def is_ready(self) -> bool:
        """Check if the service is ready to process analyses."""
        # This check remains relevant
        return self.regulation_manager.get_regulation_index() is not None
    
    def get_regulations_info(self) -> Dict[str, Any]:
        """Get information about all indexed regulations."""
        return self.regulation_manager.get_regulations_info()
    
    def rebuild_regulations_index(self, force: bool = False) -> Dict[str, Any]:
        """Rebuild the regulations index."""
        return self.regulation_manager.rebuild_index(force=force)
    
    def get_regulations_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get regulations in a specific category."""
        regulations = self.regulation_manager.get_regulation_by_category(category)
        return [reg.to_dict() for reg in regulations]