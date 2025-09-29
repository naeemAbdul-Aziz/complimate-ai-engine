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
from reporting.report_generator import generate_report, generate_text_report, generate_pdf_report

from config import settings
from utils import LoggerMixin, log_performance
from api.models.schemas import AnalysisStatus, ViolationModel


class AnalysisService(LoggerMixin):
    """Service class for handling contract compliance analysis."""
    
    def __init__(self):
        self.regulation_index: Optional[VectorStoreIndex] = None
        self.active_analyses: Dict[str, Dict[str, Any]] = {}
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize OpenAI models and regulation index."""
        try:
            self.logger.info("Initializing OpenAI models and regulation index...")
            
            # Initialize OpenAI models
            Settings.llm = OpenAI(
                model=settings.OPENAI_MODEL,
                api_key=settings.OPENAI_API_KEY,
                request_timeout=settings.OPENAI_REQUEST_TIMEOUT
            )
            Settings.embed_model = OpenAIEmbedding(
                model=settings.OPENAI_EMBEDDING_MODEL,
                api_key=settings.OPENAI_API_KEY
            )
            
            # Load and index regulation
            self._load_regulation_index()
            
            self.logger.info("Models initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize models: {e}")
            raise
    
    def _load_regulation_index(self) -> None:
        """Load regulation document and create searchable index."""
        try:
            if not settings.REGULATION_FILE.exists():
                raise FileNotFoundError(f"Regulation file not found: {settings.REGULATION_FILE}")
            
            # Load regulation text
            from PyPDF2 import PdfReader
            
            text = ""
            with open(settings.REGULATION_FILE, "rb") as file:
                reader = PdfReader(file)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            if not text.strip():
                raise ValueError("No text extracted from regulation file")
            
            # Create index
            regulation_document = Document(text=text, doc_id=str(settings.REGULATION_FILE))
            self.regulation_index = VectorStoreIndex.from_documents([regulation_document])
            
            self.logger.info(f"Regulation index created successfully ({len(text)} characters)")
            
        except Exception as e:
            self.logger.error(f"Failed to load regulation index: {e}")
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
            
            # Parse contract
            contract_nodes = parse_contract(analysis["file_path"])
            if not contract_nodes:
                raise ValueError("No content could be extracted from the contract")
            
            # Generate prompts and tasks
            analysis["progress"] = f"Generating analysis prompts for {len(contract_nodes)} sections..."
            
            tasks = []
            prompt_metadata_list = []
            
            for node in contract_nodes:
                contract_content = node.get_content()
                if not contract_content or contract_content.isspace():
                    continue
                
                # Find relevant regulations
                relevant_regs = find_relevant_regulations(
                    node, 
                    self.regulation_index, 
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
                    tasks.append(Settings.llm.acomplete(prompt))
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
                return
            
            # Execute LLM analysis
            analysis["progress"] = f"Processing {len(tasks)} compliance checks with AI..."
            
            batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process responses
            typed_batch_responses = [
                resp if isinstance(resp, (CompletionResponse, Exception)) 
                else Exception(f"Unknown response type: {type(resp)}")
                for resp in batch_responses
            ]
            
            all_violations = process_batch_violation_responses(typed_batch_responses, prompt_metadata_list)
            
            # Generate reports
            analysis["progress"] = "Generating compliance reports..."
            
            report_data = self._create_report_data(
                analysis["contract_name"],
                analysis["file_path"],
                all_violations,
                len(tasks),
                typed_batch_responses
            )
            
            # Save reports
            report_paths = await self._generate_reports(analysis_id, report_data)
            
            # Update analysis with results
            analysis["status"] = AnalysisStatus.COMPLETED
            analysis["completed_at"] = datetime.datetime.now()
            analysis["progress"] = "Analysis completed successfully"
            analysis["results"] = self._create_analysis_summary(all_violations, analysis)
            analysis["report_paths"] = report_paths
            
            self.logger.info(f"Analysis {analysis_id} completed successfully")
            
        except Exception as e:
            self.logger.error(f"Analysis {analysis_id} failed: {e}")
            analysis["status"] = AnalysisStatus.ERROR
            analysis["progress"] = "Analysis failed"
            analysis["error"] = str(e)
            analysis["completed_at"] = datetime.datetime.now()
    
    def _create_report_data(
        self, 
        contract_name: str, 
        file_path: str, 
        violations: List[dict], 
        total_prompts: int, 
        batch_responses: List
    ) -> dict:
        """Create report data structure."""
        successful_responses = sum(1 for r in batch_responses if not isinstance(r, Exception))
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
            "json": settings.REPORTS_DIR / f"{base_name}_report.json",
            "txt": settings.REPORTS_DIR / f"{base_name}_report.txt",
            "pdf": settings.REPORTS_DIR / f"{base_name}_report.pdf"
        }
        
        # Generate reports
        generate_report(report_data, str(report_paths["json"]))
        generate_text_report(report_data, str(report_paths["txt"]))
        generate_pdf_report(report_data, str(report_paths["pdf"]))
        
        # Convert to strings for JSON serialization
        return {k: str(v) for k, v in report_paths.items()}
    
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
        return self.regulation_index is not None