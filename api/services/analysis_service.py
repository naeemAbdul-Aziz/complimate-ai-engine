# api/services/analysis_service.py
"""
Analysis service for CompliMate AI Engine
========================================

This module contains the business logic for contract compliance analysis.
"""

import asyncio
import uuid
import datetime
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

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
# --- ADDED ---
from utils.circuit_breaker import SimpleCircuitBreaker
# --- END ADDED ---
from api.models.schemas import AnalysisStatus, ViolationModel
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
        self.active_analyses: Dict[str, Dict[str, Any]] = {}
        self._initialize_models()
        # --- ADDED ---
        # Initialize Circuit Breaker using settings
        self.openai_breaker = SimpleCircuitBreaker(
            fail_threshold=settings.CIRCUIT_BREAKER_FAIL_THRESHOLD,
            reset_seconds=settings.CIRCUIT_BREAKER_RESET_SECONDS
        )
        # --- END ADDED ---
    
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
                # Don't raise an error - allow the API to start and regulations can be built later
            else:
                self.logger.info("Regulation index loaded successfully")
            
            self.logger.info("Models initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize models: {e}")
            raise
    
    @log_performance
    async def start_analysis(self, file_path: str, contract_name: str) -> str:
        """
        Start a new contract analysis.
        
        Args:
            file_path: Path to the contract file
            contract_name: Name of the contract file
            
        Returns:
            Analysis ID
        """
        analysis_id = str(uuid.uuid4())
        
        # Initialize analysis record
        self.active_analyses[analysis_id] = {
            "id": analysis_id,
            "contract_name": contract_name,
            "file_path": file_path,
            "status": AnalysisStatus.STARTED,
            "progress": "Analysis started",
            "started_at": datetime.datetime.now(),
            "estimated_completion": datetime.datetime.now() + datetime.timedelta(minutes=5),
            "results": None,
            "error": None
        }
        
        # Start analysis in background
        asyncio.create_task(self._run_analysis(analysis_id))
        
        self.logger.info(f"Started analysis {analysis_id} for contract {contract_name}")
        return analysis_id
    
    # --- MODIFIED: ADDED CIRCUIT BREAKER LOGIC ---
    async def _execute_prompt_with_semaphore(
        self, 
        prompt: str, 
        semaphore: asyncio.Semaphore
    ) -> CompletionResponse:
        """Executes a single LLM prompt call, respecting semaphore and circuit breaker."""
        async with semaphore:
            # Check circuit breaker BEFORE making the call
            if self.openai_breaker.is_open():
                self.logger.warning("OpenAI circuit breaker is open. Skipping request.")
                raise Exception("OpenAI circuit breaker is open")

            try:
                # The semaphore ensures no more than N tasks run this block at once
                response = await Settings.llm.acomplete(prompt)
                # Record success if the call completes
                self.openai_breaker.record_success()
                return response
            except Exception as e:
                # Check for rate limit (429) or server errors (5xx)
                # Note: Specific exception types depend on the 'openai' library version
                # We'll check for common indicators in the error string or type name
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
                
                # Re-raise the exception so asyncio.gather captures it
                raise e
    # --- END MODIFIED ---

    async def _run_analysis(self, analysis_id: str) -> None:
        """
        Run the actual analysis in the background.
        
        Args:
            analysis_id: ID of the analysis to run
        """
        analysis = self.active_analyses[analysis_id]
        
        try:
            # Update status
            analysis["status"] = AnalysisStatus.RUNNING
            analysis["progress"] = "Parsing contract document..."
            await self._broadcast_ws(analysis_id, "progress", {
                "stage": "parse",
                "detail": "Parsing contract document"
            })
            
            # Parse contract
            contract_nodes = parse_contract(analysis["file_path"])
            if not contract_nodes:
                raise ValueError("No content could be extracted from the contract")
            await self._broadcast_ws(analysis_id, "progress", {
                "stage": "chunk",
                "detail": "Extracted contract sections",
                "current": len(contract_nodes)
            })
            
            # Generate prompts and tasks
            analysis["progress"] = f"Generating analysis prompts for {len(contract_nodes)} sections..."
            await self._broadcast_ws(analysis_id, "progress", {
                "stage": "prompt_gen",
                "detail": "Generating prompts",
                "total": len(contract_nodes)
            })
            
            tasks = []
            prompt_metadata_list = []

            # --- MODIFIED ---
            # Define a semaphore to limit concurrent requests to OpenAI
            # Read limit from settings
            concurrency_limit = settings.OPENAI_CONCURRENCY_LIMIT
            semaphore = asyncio.Semaphore(concurrency_limit)
            self.logger.info(f"Using semaphore to limit LLM concurrency to {concurrency_limit} tasks.")
            # --- END MODIFIED ---
            
            for node in contract_nodes:
                contract_content = node.get_content()
                if not contract_content or contract_content.isspace():
                    continue
                
                # Find relevant regulations
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
                    
                    # Create prompt
                    prompt = create_violation_prompt(contract_content, reg_content, reg_metadata)
                    
                    # Create async task
                    # --- MODIFIED ---
                    # Original: tasks.append(Settings.llm.acomplete(prompt))
                    # Fixed: Wrap the task in our semaphore helper
                    tasks.append(self._execute_prompt_with_semaphore(prompt, semaphore))
                    # --- END MODIFIED ---

                    prompt_metadata_list.append({
                        "contract_node_id": node.node_id,
                        "regulation_node_id": reg_node.node_id,
                        "contract_clause_snippet": contract_content[:300] + "...",
                        "regulation_excerpt_snippet": reg_content[:300] + "...",
                    })
            
            if not tasks:
                analysis["progress"] = "No analysis needed - contract appears compliant"
                analysis["status"] = AnalysisStatus.COMPLETED
                analysis["completed_at"] = datetime.datetime.now()
                await self._broadcast_ws(analysis_id, "complete", {
                    "violations": 0,
                    "duration_seconds": (analysis["completed_at"] - analysis["started_at"]).total_seconds()
                })
                return
            
            # Execute LLM analysis
            analysis["progress"] = f"Processing {len(tasks)} compliance checks with AI..."
            await self._broadcast_ws(analysis_id, "progress", {
                "stage": "llm",
                "detail": "Submitting compliance checks",
                "total": len(tasks)
            })
            
            # This will now respect the semaphore, running only N tasks at a time
            batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # --- MODIFIED: Process responses with circuit breaker awareness ---
            typed_batch_responses = []
            breaker_failures = 0
            other_failures = 0
            
            for resp in batch_responses:
                if isinstance(resp, Exception):
                    if "OpenAI circuit breaker is open" in str(resp):
                        breaker_failures += 1
                    else:
                        other_failures += 1
                    typed_batch_responses.append(resp) # Keep exceptions for processing
                elif isinstance(resp, CompletionResponse):
                    typed_batch_responses.append(resp)
                else:
                    other_failures += 1
                    typed_batch_responses.append(Exception(f"Unknown response type: {type(resp)}"))

            if breaker_failures > 0:
                self.logger.warning(f"{breaker_failures}/{len(tasks)} tasks skipped due to open circuit breaker.")
            if other_failures > 0:
                self.logger.warning(f"{other_failures}/{len(tasks)} tasks failed with other errors.")
            # --- END MODIFIED ---
            
            all_violations = process_batch_violation_responses(typed_batch_responses, prompt_metadata_list)
            await self._broadcast_ws(analysis_id, "progress", {
                "stage": "violations",
                "detail": "Aggregated potential violations",
                "current": len(all_violations)
            })
            
            # Generate reports
            analysis["progress"] = "Generating compliance reports..."
            await self._broadcast_ws(analysis_id, "progress", {
                "stage": "reporting",
                "detail": "Generating reports"
            })
            
            report_data = self._create_report_data(
                analysis["contract_name"],
                analysis["file_path"],
                all_violations,
                len(tasks),
                typed_batch_responses # Pass the list containing exceptions
            )
            
            # Save reports
            report_paths = await self._generate_reports(analysis_id, report_data)
            
            # Update analysis with results
            analysis["status"] = AnalysisStatus.COMPLETED
            analysis["completed_at"] = datetime.datetime.now()
            analysis["progress"] = "Analysis completed successfully"
            analysis["results"] = self._create_analysis_summary(all_violations, analysis)
            analysis["report_paths"] = report_paths
            await self._broadcast_ws(analysis_id, "complete", {
                "violations": len(all_violations),
                "duration_seconds": (analysis["completed_at"] - analysis["started_at"]).total_seconds()
            })
            
            self.logger.info(f"Analysis {analysis_id} completed successfully")
            
        except Exception as e:
            self.logger.error(f"Analysis {analysis_id} failed: {e}")
            analysis["status"] = AnalysisStatus.ERROR
            analysis["completed_at"] = datetime.datetime.now()
            
            # --- MODIFIED: Custom error for circuit breaker failure ---
            if "OpenAI circuit breaker is open" in str(e):
                analysis["progress"] = "Analysis failed due to API errors"
                analysis["error"] = "Analysis failed due to sustained OpenAI API issues (Circuit Breaker Open)."
                await self._broadcast_ws(analysis_id, "error", {
                    "message": analysis["error"],
                    "retryable": False # Sustained issue
                })
            else:
                analysis["progress"] = "Analysis failed"
                analysis["error"] = str(e)
                await self._broadcast_ws(analysis_id, "error", {
                    "message": str(e),
                    "retryable": True # Assume most other errors might be retryable
                })
            # --- END MODIFIED ---

    async def _broadcast_ws(self, analysis_id: str, event_type: str, payload: dict) -> None:
        """Helper to broadcast a WebSocket event if enabled and manager is available."""
        try:
            if not settings.ENABLE_WEBSOCKETS:
                return
            if ws_manager is None or WebSocketEvent is None:
                return
            evt = WebSocketEvent(type=event_type, analysis_id=analysis_id, payload=payload, schema_version=1)
            # Throttle high-frequency progress updates to reduce client load
            if event_type == "progress" and hasattr(ws_manager, "broadcast_throttled"):
                await ws_manager.broadcast_throttled(analysis_id, evt)
            else:
                await ws_manager.broadcast(analysis_id, evt)
        except Exception:
            # Don't fail analysis due to WS issues
            pass
    
    def _create_report_data(
        self, 
        contract_name: str, 
        file_path: str, 
        violations: List[dict], 
        total_prompts: int, 
        batch_responses: List # Now contains CompletionResponse or Exception
    ) -> dict:
        """Create report data structure."""
        # --- MODIFIED: Count successes/failures from the mixed list ---
        successful_responses = sum(1 for r in batch_responses if isinstance(r, CompletionResponse))
        failed_responses = sum(1 for r in batch_responses if isinstance(r, Exception))
        # --- END MODIFIED ---
        
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
        
        # Generate reports
        generate_report(report_data, str(report_paths["json_file"]))
        generate_text_report(report_data, str(report_paths["txt"]))
        generate_pdf_report(report_data, str(report_paths["pdf"]))
        
        # Convert to web URLs for the mounted /reports static path
        def to_url(p: Path) -> str:
            return f"/reports/{p.name}"
        return {k: to_url(v) for k, v in report_paths.items()}
    
    def _create_analysis_summary(self, violations: List[dict], analysis: dict) -> dict:
        """Create analysis results summary."""
        severity_counts = {"High": 0, "Medium": 0, "Low": 0}
        
        for violation in violations:
            severity = violation.get("severity", "Medium")
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        duration = None
        if analysis.get("completed_at") and analysis.get("started_at"):
            duration_seconds = (analysis["completed_at"] - analysis["started_at"]).total_seconds()
            duration = f"{duration_seconds / 60:.1f} minutes"
        
        return {
            "total_violations": len(violations),
            "high_severity": severity_counts["High"],
            "medium_severity": severity_counts["Medium"],
            "low_severity": severity_counts["Low"],
            "analysis_duration": duration or "Unknown"
        }
    
    def get_analysis_status(self, analysis_id: str) -> Optional[dict]:
        """Get the current status of an analysis."""
        return self.active_analyses.get(analysis_id)
    
    def get_analysis_results(self, analysis_id: str) -> Optional[dict]:
        """Get detailed results of a completed analysis."""
        analysis = self.active_analyses.get(analysis_id)
        if not analysis or analysis["status"] != AnalysisStatus.COMPLETED:
            return None
        
        # Return the full report data
        return analysis
    
    def list_active_analyses(self) -> List[dict]:
        """Get list of all active and recent analyses."""
        return [
            {
                "analysis_id": analysis["id"],
                "contract_name": analysis["contract_name"],
                "status": analysis["status"],
                "started_at": analysis["started_at"],
                "progress": analysis["progress"]
            }
            for analysis in self.active_analyses.values()
        ]
    
    def cleanup_old_analyses(self, max_age_hours: int = 24) -> int:
        """Clean up old analysis records."""
        current_time = datetime.datetime.now()
        max_age = datetime.timedelta(hours=max_age_hours)
        
        to_remove = []
        for analysis_id, analysis in self.active_analyses.items():
            if analysis.get("completed_at"):
                age = current_time - analysis["completed_at"]
                if age > max_age:
                    to_remove.append(analysis_id)
        
        for analysis_id in to_remove:
            del self.active_analyses[analysis_id]
        
        self.logger.info(f"Cleaned up {len(to_remove)} old analysis records")
        return len(to_remove)
    
    @property
    def is_ready(self) -> bool:
        """Check if the service is ready to process analyses."""
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