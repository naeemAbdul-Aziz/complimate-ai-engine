# api.py
import os
import json
import asyncio
import logging
import datetime
import tempfile
import uuid
from typing import List, Optional, Union, Any
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Import CompliMate engine modules
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.base.llms.types import CompletionResponse
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from PyPDF2 import PdfReader

from engine.parsing import parse_contract
from engine.retrieval import find_relevant_regulations
from engine.violation import create_violation_prompt, process_batch_violation_responses
from reporting.report_generator import generate_report, generate_text_report, generate_pdf_report

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

if not openai_api_key:
    logger.error("OPENAI_API_KEY not found in environment variables")
    raise ValueError("OPENAI_API_KEY is required")

# Constants
REGULATION_FILE = "data/regulations/li_2204.pdf"
UPLOADS_FOLDER = "uploads"
REPORTS_FOLDER = "reports"

# Ensure directories exist
os.makedirs(UPLOADS_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)

# Global variables for regulation index (loaded once)
regulation_index = None
regulation_loaded = False

# Pydantic models for API responses
class AnalysisStatus(BaseModel):
    status: str
    message: str
    analysis_id: Optional[str] = None
    contract_name: Optional[str] = None
    progress: Optional[str] = None

class ContractUploadResponse(BaseModel):
    message: str
    filename: str
    file_id: str
    file_path: str

class AnalysisRequest(BaseModel):
    file_id: str
    contract_name: Optional[str] = None

class ViolationDetail(BaseModel):
    description: str
    category: str
    regulation_ref: str
    severity: str
    type: str
    contract_node_id: Optional[str] = None
    regulation_node_id: Optional[str] = None
    contract_snippet: Optional[str] = None
    regulation_snippet: Optional[str] = None

class AnalysisReport(BaseModel):
    contract_name: str
    contract_path: str
    regulation_file: str
    analysis_timestamp: str
    total_prompts_sent: int
    successful_responses: int
    failed_responses: int
    potential_issues_found: int
    violations: List[ViolationDetail]

# Storage for active analyses
active_analyses = {}

# Initialize FastAPI app
app = FastAPI(
    title="CompliMate AI Engine API",
    description="AI-powered contract compliance analysis for Ghana's petroleum sector",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_regulation_text(file_path: str) -> str:
    """Load regulation text from PDF file."""
    try:
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
    except Exception as e:
        logger.error(f"Error loading regulation file {file_path}: {e}")
        return ""

async def initialize_regulation_index():
    """Initialize the regulation index once at startup."""
    global regulation_index, regulation_loaded
    
    if regulation_loaded:
        return
    
    try:
        logger.info("Initializing OpenAI models and regulation index...")
        
        # Initialize OpenAI models
        Settings.llm = OpenAI(model="gpt-4", api_key=openai_api_key, request_timeout=180.0)
        Settings.embed_model = OpenAIEmbedding(model="text-embedding-ada-002", api_key=openai_api_key)
        
        # Load regulation
        regulation_text = load_regulation_text(REGULATION_FILE)
        if not regulation_text:
            raise ValueError("Failed to load regulation text")
        
        # Create regulation index
        regulation_document = Document(text=regulation_text, doc_id=REGULATION_FILE)
        regulation_index = VectorStoreIndex.from_documents([regulation_document])
        regulation_loaded = True
        
        logger.info("Regulation index initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing regulation index: {e}")
        raise

@app.on_event("startup")
async def startup_event():
    """Initialize the regulation index on startup."""
    await initialize_regulation_index()

# API Endpoints

@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information."""
    return {
        "message": "CompliMate AI Engine API",
        "version": "1.0.0",
        "description": "AI-powered contract compliance analysis for Ghana's petroleum sector",
        "docs": "/docs",
        "regulation_loaded": regulation_loaded
    }

@app.get("/health", response_model=dict)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "regulation_loaded": regulation_loaded,
        "openai_configured": bool(openai_api_key)
    }

@app.post("/upload", response_model=ContractUploadResponse)
async def upload_contract(file: UploadFile = File(...)):
    """Upload a contract file for analysis."""
    try:
        # Validate file type
        if not file.filename or not file.filename.lower().endswith(('.pdf', '.txt', '.docx')):
            raise HTTPException(
                status_code=400, 
                detail="Only PDF, TXT, and DOCX files are supported"
            )
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        file_extension = Path(file.filename or "unknown.pdf").suffix
        stored_filename = f"{file_id}{file_extension}"
        file_path = os.path.join(UPLOADS_FOLDER, stored_filename)
        
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"File uploaded successfully: {file.filename} -> {stored_filename}")
        
        return ContractUploadResponse(
            message="File uploaded successfully",
            filename=file.filename or "unknown",
            file_id=file_id,
            file_path=file_path
        )
        
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

@app.post("/analyze", response_model=AnalysisStatus)
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start compliance analysis for an uploaded contract."""
    try:
        # Check if regulation index is loaded
        if not regulation_loaded or regulation_index is None:
            raise HTTPException(status_code=503, detail="Regulation index not loaded")
        
        # Find uploaded file
        file_extension = None
        for ext in ['.pdf', '.txt', '.docx']:
            potential_path = os.path.join(UPLOADS_FOLDER, f"{request.file_id}{ext}")
            if os.path.exists(potential_path):
                file_path = potential_path
                file_extension = ext
                break
        
        if not file_extension:
            raise HTTPException(status_code=404, detail="Uploaded file not found")
        
        # Generate analysis ID
        analysis_id = str(uuid.uuid4())
        contract_name = request.contract_name or f"contract_{request.file_id}"
        
        # Store analysis status
        active_analyses[analysis_id] = {
            "status": "started",
            "contract_name": contract_name,
            "file_path": file_path,
            "start_time": datetime.datetime.now(),
            "progress": "Initializing analysis..."
        }
        
        # Start background analysis
        background_tasks.add_task(perform_analysis, analysis_id, file_path, contract_name)
        
        return AnalysisStatus(
            status="started",
            message="Analysis started successfully",
            analysis_id=analysis_id,
            contract_name=contract_name,
            progress="Analysis queued for processing"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Error starting analysis: {str(e)}")

async def perform_analysis(analysis_id: str, file_path: str, contract_name: str):
    """Background task to perform contract analysis."""
    try:
        # Update status
        active_analyses[analysis_id]["status"] = "parsing"
        active_analyses[analysis_id]["progress"] = "Parsing contract document..."
        
        # Parse contract
        contract_nodes = parse_contract(file_path)
        if not contract_nodes:
            active_analyses[analysis_id]["status"] = "failed"
            active_analyses[analysis_id]["error"] = "No content could be parsed from contract"
            return
        
        # Update status
        active_analyses[analysis_id]["status"] = "analyzing"
        active_analyses[analysis_id]["progress"] = f"Analyzing {len(contract_nodes)} contract sections..."
        
        # Generate analysis tasks
        tasks = []
        prompt_metadata_list = []
        
        for node in contract_nodes:
            contract_content = node.get_content()
            if not contract_content or contract_content.isspace():
                continue
            
            # Find relevant regulations
            relevant_regs = find_relevant_regulations(node, regulation_index)
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
                
                # Add task
                tasks.append(Settings.llm.acomplete(prompt))
                prompt_metadata_list.append({
                    "contract_node_id": node.node_id,
                    "regulation_node_id": reg_node.node_id,
                    "contract_clause_snippet": contract_content[:300] + "...",
                    "regulation_excerpt_snippet": reg_content[:300] + "...",
                })
        
        if not tasks:
            active_analyses[analysis_id]["status"] = "completed"
            active_analyses[analysis_id]["violations"] = []
            active_analyses[analysis_id]["report_data"] = create_report_data(contract_name, file_path, [])
            return
        
        # Update status
        active_analyses[analysis_id]["progress"] = f"Processing {len(tasks)} compliance checks with AI..."
        
        # Execute LLM analysis
        batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process responses (cast to correct type)
        typed_batch_responses: List[Union[CompletionResponse, Exception]] = [
            resp if isinstance(resp, (CompletionResponse, Exception)) else Exception(f"Unknown response type: {type(resp)}")
            for resp in batch_responses
        ]
        all_violations = process_batch_violation_responses(typed_batch_responses, prompt_metadata_list)
        
        # Create report data
        report_data = create_report_data(contract_name, file_path, all_violations, len(tasks), batch_responses)
        
        # Generate reports
        base_report_name = f"{contract_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        json_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.json")
        txt_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.txt")
        pdf_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.pdf")
        
        generate_report(report_data, json_report_path)
        generate_text_report(report_data, txt_report_path)
        generate_pdf_report(report_data, pdf_report_path)
        
        # Update final status
        active_analyses[analysis_id].update({
            "status": "completed",
            "progress": "Analysis completed successfully",
            "violations": all_violations,
            "report_data": report_data,
            "json_report_path": json_report_path,
            "txt_report_path": txt_report_path,
            "pdf_report_path": pdf_report_path,
            "end_time": datetime.datetime.now()
        })
        
        logger.info(f"Analysis completed for {analysis_id}: {len(all_violations)} violations found")
        
    except Exception as e:
        logger.error(f"Error in analysis {analysis_id}: {e}")
        active_analyses[analysis_id]["status"] = "failed"
        active_analyses[analysis_id]["error"] = str(e)

def create_report_data(contract_name: str, file_path: str, violations: list, total_prompts: int = 0, batch_responses: Optional[list] = None) -> dict:
    """Create report data structure."""
    successful_responses = 0
    failed_responses = 0
    
    if batch_responses:
        successful_responses = sum(1 for r in batch_responses if not isinstance(r, Exception))
        failed_responses = sum(1 for r in batch_responses if isinstance(r, Exception))
    
    return {
        "contract_name": contract_name,
        "contract_path": file_path,
        "regulation_file": REGULATION_FILE,
        "analysis_timestamp": datetime.datetime.now().isoformat(),
        "total_prompts_sent": total_prompts,
        "successful_responses": successful_responses,
        "failed_responses": failed_responses,
        "potential_issues_found": len(violations),
        "violations": violations,
    }

@app.get("/analysis/{analysis_id}/status", response_model=AnalysisStatus)
async def get_analysis_status(analysis_id: str):
    """Get the status of an ongoing analysis."""
    if analysis_id not in active_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = active_analyses[analysis_id]
    
    return AnalysisStatus(
        status=analysis["status"],
        message=analysis.get("error", "Analysis in progress"),
        analysis_id=analysis_id,
        contract_name=analysis.get("contract_name"),
        progress=analysis.get("progress")
    )

@app.get("/analysis/{analysis_id}/report", response_model=AnalysisReport)
async def get_analysis_report(analysis_id: str):
    """Get the analysis report in JSON format."""
    if analysis_id not in active_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = active_analyses[analysis_id]
    
    if analysis["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed yet")
    
    return AnalysisReport(**analysis["report_data"])

@app.get("/analysis/{analysis_id}/report/pdf")
async def get_analysis_report_pdf(analysis_id: str):
    """Download the analysis report as PDF."""
    if analysis_id not in active_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = active_analyses[analysis_id]
    
    if analysis["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed yet")
    
    pdf_path = analysis.get("pdf_report_path")
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not found")
    
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{analysis['contract_name']}_compliance_report.pdf"
    )

@app.get("/analysis/{analysis_id}/report/txt")
async def get_analysis_report_txt(analysis_id: str):
    """Download the analysis report as text file."""
    if analysis_id not in active_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = active_analyses[analysis_id]
    
    if analysis["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed yet")
    
    txt_path = analysis.get("txt_report_path")
    if not txt_path or not os.path.exists(txt_path):
        raise HTTPException(status_code=404, detail="Text report not found")
    
    return FileResponse(
        txt_path,
        media_type="text/plain",
        filename=f"{analysis['contract_name']}_compliance_report.txt"
    )

@app.get("/analyses", response_model=List[dict])
async def list_analyses():
    """List all analyses with their current status."""
    analyses_list = []
    for analysis_id, analysis in active_analyses.items():
        analyses_list.append({
            "analysis_id": analysis_id,
            "contract_name": analysis.get("contract_name"),
            "status": analysis["status"],
            "start_time": analysis.get("start_time", "").isoformat() if analysis.get("start_time") else None,
            "end_time": analysis.get("end_time", "").isoformat() if analysis.get("end_time") else None,
            "violations_found": len(analysis.get("violations", [])),
            "progress": analysis.get("progress")
        })
    
    return analyses_list

@app.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """Delete an analysis and its associated files."""
    if analysis_id not in active_analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    analysis = active_analyses[analysis_id]
    
    # Clean up report files
    for report_path_key in ["json_report_path", "txt_report_path", "pdf_report_path"]:
        report_path = analysis.get(report_path_key)
        if report_path and os.path.exists(report_path):
            try:
                os.remove(report_path)
            except Exception as e:
                logger.warning(f"Could not delete report file {report_path}: {e}")
    
    # Remove from active analyses
    del active_analyses[analysis_id]
    
    return {"message": f"Analysis {analysis_id} deleted successfully"}

if __name__ == "__main__":
    import uvicorn
    
    # For development
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
