# api/services/analysis_service.py
"""
Analysis service for CompliMate AI Engine - DB Persistence Version
=================================================================

This module contains the business logic for contract compliance analysis,
now using a database for state persistence.
"""

import asyncio
import uuid
import datetime
import os
import time # For manual performance logging
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path

# --- SQLModel/SQLAlchemy Imports ---
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy import desc
# --- End DB Imports ---

# --- LlamaIndex Imports ---
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.base.llms.types import CompletionResponse
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
# --- End LlamaIndex Imports ---

# --- Engine/Project Imports ---
from engine.parsing import parse_contract
from engine.retrieval import find_relevant_regulations
from engine.violation import create_violation_prompt, process_batch_violation_responses
from engine.regulation_manager import RegulationManager
from reporting.report_generator import generate_report, generate_text_report, generate_pdf_report

from config import settings
from config.logger import get_component_logger, log_performance
from utils.circuit_breaker import SimpleCircuitBreaker
from api.models.schemas import AnalysisStatus, ViolationModel
from api.models.db_models import Analysis
# --- End Project Imports ---

# Optional import for WebSocket broadcasting (decoupled)
_ws_import_failed = False
try:
    from api.realtime import manager as ws_manager
    from api.models.schemas import WebSocketEvent
except ImportError:
    ws_manager = None
    WebSocketEvent = None
    _ws_import_failed = True
except Exception as ws_import_exc:
    ws_manager = None
    WebSocketEvent = None
    _ws_import_failed = True


class AnalysisService:
    """Service class for handling contract compliance analysis with DB persistence."""

    def __init__(self):
        self._component_logger = get_component_logger('analysis_service')
        if _ws_import_failed:
            self.logger.warning("WebSocket modules failed to import. Realtime updates disabled.")

        self.regulation_manager = RegulationManager()
        self._initialize_models()

        self.openai_breaker = SimpleCircuitBreaker(
            fail_threshold=settings.CIRCUIT_BREAKER_FAIL_THRESHOLD,
            reset_seconds=settings.CIRCUIT_BREAKER_RESET_SECONDS
        )
        self.logger.info("AnalysisService initialized.")

    @property
    def logger(self):
        """Get the component logger."""
        return self._component_logger

    def _initialize_models(self) -> None:
        """Initialize OpenAI models and regulation index."""
        self.logger.info("Attempting to initialize OpenAI models and regulation index...")
        if not settings.OPENAI_API_KEY:
             self.logger.error("OPENAI_API_KEY is not set. Cannot initialize OpenAI models.")
             raise ValueError("OpenAI API key missing, cannot initialize LLM/Embedding models.")

        try:
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
            self.logger.info("OpenAI LLM and Embedding models configured.")

            regulation_index = self.regulation_manager.get_regulation_index()
            if regulation_index is None:
                self.logger.warning("Regulation index is not available. Analysis may fail until index is built.")
            else:
                self.logger.info("Regulation index loaded or built successfully.")

            self.logger.info("Model and index initialization complete.")

        except Exception as e:
            self.logger.exception(f"CRITICAL: Failed during model/index initialization: {e}")
            raise

    # --- start_analysis ---
    async def start_analysis(self, session: AsyncSession, file_path: str, contract_name: str) -> str:
        """
        Start a new contract analysis by creating a record in the database.
        """
        op_start_time = time.monotonic()
        success = False
        analysis_id_str = "N/A"

        self.logger.info(f"Starting analysis process for contract: {contract_name} ({file_path})")
        try:
            new_analysis = Analysis(
                contract_name=contract_name,
                file_path=file_path,
                status=AnalysisStatus.STARTED,
                progress="Analysis requested"
            )
            session.add(new_analysis)
            await session.commit()
            await session.refresh(new_analysis)

            analysis_id_str = str(new_analysis.id)
            self.logger.info(f"Created analysis record in DB with ID: {analysis_id_str}")

            # Enqueue background processing via Celery if enabled, else fallback to asyncio task
            if getattr(settings, "ENABLE_CELERY", False):
                try:
                    from tasks.analysis_tasks import run_analysis_task  # Local import to avoid mandatory dependency
                    run_analysis_task.delay(analysis_id_str)
                    self.logger.info(f"Celery task enqueued for analysis {analysis_id_str}")
                except Exception as celery_err:
                    self.logger.warning(f"Celery enqueue failed ({celery_err}); falling back to asyncio task.")
                    asyncio.create_task(self._run_analysis(analysis_id_str))
                    self.logger.info(f"Asyncio background task scheduled for analysis {analysis_id_str}")
            else:
                asyncio.create_task(self._run_analysis(analysis_id_str))
                self.logger.info(f"Asyncio background task scheduled for analysis {analysis_id_str}")

            success = True
            return analysis_id_str
        except Exception as e:
            self.logger.exception(f"Failed to create analysis record or schedule task for {contract_name}: {e}")
            raise RuntimeError(f"Could not start analysis: {e}")
        finally:
            op_duration = time.monotonic() - op_start_time
            log_performance(
                operation="start_analysis",
                duration=op_duration,
                success=success,
                extra_data={"contract_name": contract_name, "analysis_id": analysis_id_str}
            )


    # --- _execute_prompt_with_semaphore ---
    async def _execute_prompt_with_semaphore(
        self,
        prompt: str,
        semaphore: asyncio.Semaphore
    ) -> CompletionResponse:
        """Executes a single LLM prompt call, respecting semaphore and circuit breaker."""
        async with semaphore:
            if self.openai_breaker.is_open():
                self.logger.warning("OpenAI circuit breaker is open. Skipping LLM request.")
                raise RuntimeError("OpenAI circuit breaker is open")

            try:
                response = await Settings.llm.acomplete(prompt)
                self.openai_breaker.record_success()
                return response
            except Exception as e:
                error_str = str(e).lower()
                error_type_name = type(e).__name__.lower()
                status_code = getattr(e, 'status_code', None)

                if status_code == 429 or "ratelimiterror" in error_type_name:
                    self.logger.warning(f"OpenAI Rate Limit Error encountered: {e}")
                    self.openai_breaker.record_failure()
                elif status_code in [500, 502, 503, 504] or \
                     "servererror" in error_type_name or \
                     "timeouterror" in error_type_name or \
                     isinstance(e, asyncio.TimeoutError):
                    self.logger.error(f"OpenAI Server/Timeout Error encountered: {e}")
                    self.openai_breaker.record_failure()
                elif status_code and 400 <= status_code < 500 and status_code != 429:
                     self.logger.error(f"OpenAI Client Error (e.g., auth, bad request): {e}")
                else:
                    self.logger.exception(f"Unhandled OpenAI API Error: {e}")

                raise e


    # --- _run_analysis (Background Task) ---
    async def _run_analysis(self, analysis_id_str: str) -> None:
        """
        Run the actual analysis in the background using a dedicated DB session.
        """
        from api.db import AsyncSessionLocal

        analysis_id: Optional[uuid.UUID] = None
        analysis: Optional[Analysis] = None
        used_regulation_files = set()

        try:
            analysis_id = uuid.UUID(analysis_id_str)
        except ValueError:
            self.logger.error(f"Invalid UUID received for background task: {analysis_id_str}")
            return

        self.logger.info(f"Background task started for analysis ID: {analysis_id}")

        async with AsyncSessionLocal() as session:
            try:
                analysis = await session.get(Analysis, analysis_id)
                if not analysis:
                    self.logger.error(f"Analysis {analysis_id} not found in DB for background run.")
                    return

                # --- Start Analysis Steps ---
                self.logger.debug(f"[{analysis_id}] Setting status to RUNNING")
                analysis.status = AnalysisStatus.RUNNING
                analysis.progress = "Parsing contract document..."
                await session.commit()
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "parse", "detail": analysis.progress
                })

                # --- Parse Contract ---
                self.logger.debug(f"[{analysis_id}] Parsing contract file: {analysis.file_path}")
                contract_nodes = list(parse_contract(analysis.file_path))
                if not contract_nodes:
                    raise ValueError(f"No content could be extracted from contract file: {analysis.file_path}")
                self.logger.info(f"[{analysis_id}] Parsed contract into {len(contract_nodes)} nodes.")
                analysis.progress = f"Parsed into {len(contract_nodes)} sections."
                await session.commit()
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "chunk", "detail": "Extracted contract sections", "current": len(contract_nodes)
                })

                # --- Generate Prompts ---
                self.logger.debug(f"[{analysis_id}] Generating prompts for {len(contract_nodes)} nodes.")
                analysis.progress = f"Generating analysis prompts for {len(contract_nodes)} sections..."
                await session.commit()
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "prompt_gen", "detail": "Generating prompts", "total": len(contract_nodes)
                })

                tasks = []
                prompt_metadata_list = []
                concurrency_limit = settings.OPENAI_CONCURRENCY_LIMIT
                semaphore = asyncio.Semaphore(concurrency_limit)
                self.logger.info(f"[{analysis_id}] Using semaphore concurrency limit: {concurrency_limit}")

                regulation_index = self.regulation_manager.get_regulation_index()
                if regulation_index is None:
                    raise RuntimeError("Regulation index is not available. Cannot perform analysis.")

                for node_idx, node in enumerate(contract_nodes):
                    contract_content = node.get_content()
                    if not contract_content or contract_content.isspace():
                        continue

                    relevant_regs = find_relevant_regulations(
                        node, regulation_index, top_n=settings.HYBRID_SEARCH_TOP_K
                    )
                    if not relevant_regs:
                        continue

                    for reg_result in relevant_regs:
                        reg_node = reg_result.node
                        reg_content = reg_node.get_content()
                        reg_metadata = reg_node.metadata or {}
                        if not reg_content or reg_content.isspace():
                            continue
                        
                        used_regulation_files.add(reg_metadata.get("file_name", "Unknown"))

                        prompt = create_violation_prompt(contract_content, reg_content, reg_metadata)
                        tasks.append(self._execute_prompt_with_semaphore(prompt, semaphore))
                        prompt_metadata_list.append({
                            "contract_node_id": node.node_id,
                            "regulation_node_id": reg_node.node_id,
                            "contract_clause_snippet": contract_content[:300] + "...",
                            "regulation_excerpt_snippet": reg_content[:300] + "...",
                        })

                if not tasks:
                    self.logger.info(f"[{analysis_id}] No relevant regulations found or issues identified. Marking as complete.")
                    analysis.progress = "No applicable regulations found or contract appears compliant."
                    analysis.status = AnalysisStatus.COMPLETED
                    analysis.completed_at = datetime.datetime.now()
                    analysis.results = self._create_analysis_summary([], analysis)
                    analysis.report_paths = {}
                    await session.commit()
                    await self._broadcast_ws(analysis_id_str, "complete", {
                        "violations": 0,
                        "duration_seconds": (analysis.completed_at - analysis.started_at).total_seconds()
                    })
                    return

                # --- Execute LLM Calls ---
                self.logger.info(f"[{analysis_id}] Submitting {len(tasks)} LLM tasks.")
                analysis.progress = f"Processing {len(tasks)} compliance checks with AI..."
                await session.commit()
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "llm", "detail": "Submitting compliance checks", "total": len(tasks)
                })

                batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
                self.logger.info(f"[{analysis_id}] Received {len(batch_responses)} LLM responses/exceptions.")

                # --- Process Responses ---
                typed_batch_responses: List[Union[CompletionResponse, Exception]] = []
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
                        typed_batch_responses.append(TypeError(f"Unknown response type: {type(resp)}"))

                if breaker_failures > 0:
                    self.logger.warning(f"[{analysis_id}] {breaker_failures}/{len(tasks)} tasks skipped due to open circuit breaker.")
                if other_failures > 0:
                    self.logger.warning(f"[{analysis_id}] {other_failures}/{len(tasks)} tasks failed with errors other than circuit breaker.")

                all_violations = process_batch_violation_responses(typed_batch_responses, prompt_metadata_list)
                self.logger.info(f"[{analysis_id}] Extracted {len(all_violations)} potential violations.")
                analysis.progress = f"Aggregated {len(all_violations)} potential issues."
                await session.commit()
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "violations", "detail": "Aggregated potential violations", "current": len(all_violations)
                })

                # --- Generate Reports ---
                self.logger.debug(f"[{analysis_id}] Generating reports...")
                analysis.progress = "Generating compliance reports..."
                await session.commit()
                await self._broadcast_ws(analysis_id_str, "progress", {
                    "stage": "reporting", "detail": "Generating reports"
                })

                report_data = self._create_report_data(
                    analysis.contract_name,
                    analysis.file_path,
                    all_violations,
                    len(tasks),
                    typed_batch_responses,
                    list(used_regulation_files)
                )

                # --- Save Reports (Now Async) ---
                report_paths = await self._generate_reports(analysis_id_str, report_data)
                self.logger.info(f"[{analysis_id}] Reports generated: {list(report_paths.keys())}")

                # --- Final Update ---
                analysis.status = AnalysisStatus.COMPLETED
                analysis.completed_at = datetime.datetime.now()
                analysis.progress = "Analysis completed successfully"
                analysis.results = self._create_analysis_summary(all_violations, analysis)
                analysis.report_paths = report_paths
                await session.commit()
                self.logger.info(f"[{analysis_id}] Analysis completed and saved to DB.")

                await self._broadcast_ws(analysis_id_str, "complete", {
                    "violations": len(all_violations),
                    "duration_seconds": (analysis.completed_at - analysis.started_at).total_seconds()
                })

            # --- Main Exception Handling for the Background Task ---
            except Exception as e:
                self.logger.exception(f"Analysis task {analysis_id} failed critically: {e}")
                if analysis:
                    analysis.status = AnalysisStatus.ERROR
                    analysis.completed_at = datetime.datetime.now()
                    error_payload = {}
                    if "OpenAI circuit breaker is open" in str(e) or isinstance(e, RuntimeError) and "breaker" in str(e):
                        analysis.progress = "Analysis failed due to API errors"
                        analysis.error = "Analysis failed due to sustained OpenAI API issues (Circuit Breaker Open)."
                        error_payload = {"message": analysis.error, "retryable": False}
                    elif isinstance(e, ValueError) and "extracted from contract" in str(e):
                         analysis.progress = "Analysis failed: Cannot read contract"
                         analysis.error = str(e)
                         error_payload = {"message": analysis.error, "retryable": False}
                    elif isinstance(e, RuntimeError) and "Regulation index is not available" in str(e):
                         analysis.progress = "Analysis failed: Regulations not ready"
                         analysis.error = str(e)
                         error_payload = {"message": analysis.error, "retryable": True}
                    else:
                        analysis.progress = "Analysis failed"
                        analysis.error = str(e)
                        error_payload = {"message": str(e), "retryable": True}
                    try:
                        await session.commit()
                        self.logger.info(f"[{analysis_id}] Analysis error state saved to DB.")
                        await self._broadcast_ws(analysis_id_str, "error", error_payload)
                    except Exception as commit_err:
                        self.logger.error(f"[{analysis_id}] FAILED TO SAVE ERROR STATE TO DB: {commit_err}")
                else:
                    self.logger.error(f"Analysis {analysis_id} failed, but analysis object was not available to record error state.")

        self.logger.info(f"Background task finished for analysis ID: {analysis_id}")

    async def _broadcast_ws(self, analysis_id: str, event_type: str, payload: dict) -> None:
        """Helper to broadcast a WebSocket event."""
        if not settings.ENABLE_WEBSOCKETS: return
        if ws_manager is None or WebSocketEvent is None: return
        try:
            evt = WebSocketEvent(type=event_type, analysis_id=analysis_id, payload=payload, schema_version=1)
            if event_type == "progress" and hasattr(ws_manager, "broadcast_throttled"):
                await ws_manager.broadcast_throttled(analysis_id, evt)
            else:
                await ws_manager.broadcast(analysis_id, evt)
        except Exception as ws_err:
            self.logger.warning(f"[{analysis_id}] WebSocket broadcast failed for event {event_type}: {ws_err}", exc_info=False)

    def _create_report_data(
        self,
        contract_name: str,
        file_path: str,
        violations: List[dict],
        total_prompts: int,
        batch_responses: List[Union[CompletionResponse, Exception]],
        regulation_files: List[str]
    ) -> dict:
        """Create report data structure."""
        successful_responses = sum(1 for r in batch_responses if isinstance(r, CompletionResponse))
        failed_responses = sum(1 for r in batch_responses if isinstance(r, Exception))

        return {
            "contract_name": contract_name,
            "contract_path": file_path,
            "regulation_files": regulation_files,
            "analysis_timestamp": datetime.datetime.now().isoformat(),
            "total_prompts_sent": total_prompts,
            "successful_responses": successful_responses,
            "failed_responses": failed_responses,
            "potential_issues_found": len(violations),
            "violations": violations,
         }

    async def _generate_reports(self, analysis_id: str, report_data: dict) -> dict:
        """Generate all report formats asynchronously."""
        base_name = f"{report_data['contract_name']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        report_paths_abs = {
            "json_file": settings.REPORTS_DIR / f"{base_name}_report.json",
            "txt": settings.REPORTS_DIR / f"{base_name}_report.txt",
            "pdf": settings.REPORTS_DIR / f"{base_name}_report.pdf"
        }

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, generate_report, report_data, str(report_paths_abs["json_file"]))
            self.logger.debug(f"[{analysis_id}] JSON report generated.")
            await loop.run_in_executor(None, generate_text_report, report_data, str(report_paths_abs["txt"]))
            self.logger.debug(f"[{analysis_id}] TXT report generated.")
            await loop.run_in_executor(None, generate_pdf_report, report_data, str(report_paths_abs["pdf"]))
            self.logger.debug(f"[{analysis_id}] PDF report generated.")
        except Exception as report_err:
             self.logger.exception(f"[{analysis_id}] Error generating one or more reports: {report_err}")
             pass

        def to_url(p: Path) -> str:
            return f"/reports/{p.name}"

        return {k: to_url(v) for k, v in report_paths_abs.items()}

    def _create_analysis_summary(self, violations: List[dict], analysis: Analysis) -> dict:
        """Create analysis results summary using the DB model."""
        severity_counts = {"High": 0, "Medium": 0, "Low": 0, "N/A": 0}

        for violation in violations:
            severity = violation.get("severity", "N/A")
            normalized_severity = severity if severity in severity_counts else "N/A"
            severity_counts[normalized_severity] += 1

        duration = None
        if analysis.completed_at and analysis.started_at:
            try:
                if isinstance(analysis.completed_at, datetime.datetime) and isinstance(analysis.started_at, datetime.datetime):
                     duration_delta = analysis.completed_at - analysis.started_at
                     duration_seconds = duration_delta.total_seconds()
                     if duration_seconds >= 0:
                          duration = f"{duration_seconds / 60:.1f} minutes ({duration_seconds:.1f} seconds)"
                     else:
                          self.logger.warning(f"[{analysis.id}] Calculated negative duration: {duration_seconds}s. Timestamps: Start={analysis.started_at}, End={analysis.completed_at}")
                          duration = "Invalid duration"
                else:
                    self.logger.warning(f"[{analysis.id}] Invalid timestamp types for duration calculation: Start={type(analysis.started_at)}, End={type(analysis.completed_at)}")
                    duration = "Invalid timestamp format"
            except Exception as dur_err:
                 self.logger.error(f"[{analysis.id}] Error calculating analysis duration: {dur_err}")
                 duration = "Calculation error"

        return {
            "total_violations": len(violations),
            "high_severity": severity_counts["High"],
            "medium_severity": severity_counts["Medium"],
            "low_severity": severity_counts["Low"],
            "na_severity": severity_counts["N/A"],
            "analysis_duration": duration or "Unknown"
        }

    async def get_analysis_status(self, session: AsyncSession, analysis_id: str) -> Optional[Analysis]:
        """Get the current status of an analysis from the DB."""
        self.logger.debug(f"Querying status for analysis ID: {analysis_id}")
        try:
            analysis_uuid = uuid.UUID(analysis_id)
            analysis = await session.get(Analysis, analysis_uuid)
            if analysis:
                self.logger.debug(f"Status found for {analysis_id}: {analysis.status}")
            else:
                self.logger.warning(f"Status query: Analysis ID {analysis_id} not found in DB.")
            return analysis
        except ValueError:
            self.logger.warning(f"Status query: Invalid UUID format '{analysis_id}'")
            return None
        except Exception as e:
            self.logger.exception(f"Database error getting status for {analysis_id}: {e}")
            raise

    async def get_analysis_results(self, session: AsyncSession, analysis_id: str) -> Optional[Analysis]:
        """Get detailed results of a completed/failed analysis from the DB."""
        self.logger.debug(f"Querying results for analysis ID: {analysis_id}")
        try:
            analysis_uuid = uuid.UUID(analysis_id)
            analysis = await session.get(Analysis, analysis_uuid)

            if analysis and analysis.status in [AnalysisStatus.COMPLETED, AnalysisStatus.ERROR]:
                self.logger.debug(f"Results found for {analysis_id} (Status: {analysis.status})")
                return analysis
            elif analysis:
                self.logger.debug(f"Results query: Analysis {analysis_id} found but not completed (Status: {analysis.status}).")
                return None
            else:
                self.logger.warning(f"Results query: Analysis ID {analysis_id} not found in DB.")
                return None
        except ValueError:
            self.logger.warning(f"Results query: Invalid UUID format '{analysis_id}'")
            return None
        except Exception as e:
            self.logger.exception(f"Database error getting results for {analysis_id}: {e}")
            raise

    async def list_analyses(self, session: AsyncSession, limit: int = 100) -> List[Analysis]:
        """Get list of recent analyses from the DB, sorted descending by start time."""
        self.logger.debug(f"Querying list of recent analyses (limit: {limit})")
        try:
            statement = select(Analysis).order_by(getattr(Analysis, "started_at").desc()).limit(limit)
            results = await session.exec(statement)
            analyses = results.all()
            self.logger.info(f"Retrieved {len(analyses)} analysis records from DB.")
            return list(analyses)
        except Exception as e:
            self.logger.exception(f"Database error listing analyses: {e}")
            raise

    @property
    def is_ready(self) -> bool:
        """Check if the service is ready."""
        index_exists = self.regulation_manager.get_regulation_index() is not None
        models_ready = hasattr(Settings, 'llm') and Settings.llm is not None
        ready = index_exists and models_ready
        if not ready:
            self.logger.warning(f"Service ready check: Index={index_exists}, Models={models_ready} -> Ready={ready}")
        return ready

    def get_regulations_info(self) -> Dict[str, Any]:
        """Get information about all indexed regulations."""
        self.logger.debug("Passthrough: get_regulations_info")
        return self.regulation_manager.get_regulations_info()

    def rebuild_regulations_index(self, force: bool = False) -> Dict[str, Any]:
        """Rebuild the regulations index."""
        self.logger.info(f"Passthrough: rebuild_regulations_index (force={force})")
        result = self.regulation_manager.rebuild_index(force=force)
        return result

    def get_regulations_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get regulations in a specific category."""
        self.logger.debug(f"Passthrough: get_regulations_by_category (category='{category}')")
        regulations_metadata = self.regulation_manager.get_regulation_by_category(category)
        return [reg.to_dict() for reg in regulations_metadata]