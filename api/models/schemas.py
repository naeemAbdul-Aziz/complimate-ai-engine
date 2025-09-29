# api/models/schemas.py
"""
Pydantic models and schemas for the CompliMate API
================================================

This module contains all the request/response models used by the FastAPI endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class AnalysisStatus(str, Enum):
    """Analysis status enumeration."""
    PENDING = "pending"
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


class ViolationSeverity(str, Enum):
    """Violation severity levels."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    NA = "N/A"


class ViolationCategory(str, Enum):
    """Violation category types."""
    NON_COMPLIANT_CLAUSE = "Non-compliant Clause"
    MISSING_OBLIGATION = "Missing Obligation"
    AMBIGUITY = "Ambiguity"
    UNCATEGORIZED = "Uncategorized"


class ReportFormat(str, Enum):
    """Report format types."""
    JSON = "json"
    TXT = "txt"
    PDF = "pdf"


# Request Models
class AnalysisRequest(BaseModel):
    """Request model for starting an analysis."""
    file_id: str = Field(..., description="UUID of the uploaded file")
    priority: Optional[str] = Field("normal", description="Analysis priority (low, normal, high)")
    include_universal_clauses: bool = Field(True, description="Include universal clause analysis")
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "123e4567-e89b-12d3-a456-426614174000",
                "priority": "normal",
                "include_universal_clauses": True
            }
        }


# Response Models
class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Service health status")
    timestamp: datetime = Field(..., description="Current timestamp")
    regulation_loaded: bool = Field(..., description="Whether regulation index is loaded")
    openai_configured: bool = Field(..., description="Whether OpenAI is configured")
    version: str = Field("1.0.0", description="API version")


class ContractUploadResponse(BaseModel):
    """Response model for file upload."""
    message: str = Field(..., description="Success message")
    filename: str = Field(..., description="Original filename")
    file_id: str = Field(..., description="Unique file identifier")
    file_path: str = Field(..., description="Stored file path")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    uploaded_at: datetime = Field(default_factory=datetime.now, description="Upload timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "File uploaded successfully",
                "filename": "contract.pdf",
                "file_id": "123e4567-e89b-12d3-a456-426614174000",
                "file_path": "/uploads/123e4567-e89b-12d3-a456-426614174000.pdf",
                "file_size": 1024000,
                "uploaded_at": "2025-09-29T10:30:00.123456"
            }
        }


class AnalysisStartResponse(BaseModel):
    """Response model for analysis start."""
    message: str = Field(..., description="Success message")
    analysis_id: str = Field(..., description="Unique analysis identifier")
    status: AnalysisStatus = Field(..., description="Current analysis status")
    estimated_duration: str = Field(..., description="Estimated completion time")
    started_at: datetime = Field(default_factory=datetime.now, description="Analysis start time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Analysis started successfully",
                "analysis_id": "987e6543-e21b-43d2-a567-426614174111",
                "status": "started",
                "estimated_duration": "2-5 minutes",
                "started_at": "2025-09-29T10:35:00.123456"
            }
        }


class ViolationModel(BaseModel):
    """Model for a compliance violation."""
    description: str = Field(..., description="Detailed violation description")
    category: ViolationCategory = Field(..., description="Violation category")
    regulation_ref: str = Field(..., description="Regulation reference")
    severity: ViolationSeverity = Field(..., description="Violation severity")
    type: str = Field(..., description="Violation type")
    contract_node_id: Optional[str] = Field(None, description="Contract node identifier")
    regulation_node_id: Optional[str] = Field(None, description="Regulation node identifier")
    contract_snippet: Optional[str] = Field(None, description="Relevant contract text")
    regulation_snippet: Optional[str] = Field(None, description="Relevant regulation text")
    
    class Config:
        json_schema_extra = {
            "example": {
                "description": "The contract clause does not mention the requirement for a local content plan",
                "category": "Missing Obligation",
                "regulation_ref": "Regulation 33",
                "severity": "High",
                "type": "Potential Compliance Issue",
                "contract_snippet": "Contract text excerpt...",
                "regulation_snippet": "Regulation text excerpt..."
            }
        }


class AnalysisResults(BaseModel):
    """Model for analysis summary results."""
    total_violations: int = Field(..., description="Total number of violations found")
    high_severity: int = Field(..., description="Number of high severity violations")
    medium_severity: int = Field(..., description="Number of medium severity violations")
    low_severity: int = Field(..., description="Number of low severity violations")
    analysis_duration: str = Field(..., description="Actual analysis duration")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_violations": 15,
                "high_severity": 3,
                "medium_severity": 8,
                "low_severity": 4,
                "analysis_duration": "3.2 minutes"
            }
        }


class ReportPaths(BaseModel):
    """Model for report file paths."""
    json_file: str = Field(..., description="Path to JSON report")
    txt: str = Field(..., description="Path to text report")
    pdf: str = Field(..., description="Path to PDF report")


class AnalysisStatusResponse(BaseModel):
    """Response model for analysis status."""
    analysis_id: str = Field(..., description="Analysis identifier")
    status: AnalysisStatus = Field(..., description="Current status")
    progress: str = Field(..., description="Current progress description")
    started_at: datetime = Field(..., description="Analysis start time")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    completed_at: Optional[datetime] = Field(None, description="Actual completion time")
    results: Optional[AnalysisResults] = Field(None, description="Analysis results (when completed)")
    report_paths: Optional[ReportPaths] = Field(None, description="Report file paths (when completed)")
    error: Optional[str] = Field(None, description="Error message (if failed)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "analysis_id": "987e6543-e21b-43d2-a567-426614174111",
                "status": "running",
                "progress": "Processing contract nodes...",
                "started_at": "2025-09-29T10:35:00.123456",
                "estimated_completion": "2025-09-29T10:40:00.123456"
            }
        }


class AnalysisResultsResponse(BaseModel):
    """Response model for detailed analysis results."""
    contract_name: str = Field(..., description="Original contract filename")
    contract_path: str = Field(..., description="Contract file path")
    regulation_file: str = Field(..., description="Regulation file used")
    analysis_timestamp: datetime = Field(..., description="Analysis completion timestamp")
    total_prompts_sent: int = Field(..., description="Number of AI prompts sent")
    successful_responses: int = Field(..., description="Number of successful AI responses")
    failed_responses: int = Field(..., description="Number of failed AI responses")
    potential_issues_found: int = Field(..., description="Total potential issues found")
    violations: List[ViolationModel] = Field(..., description="List of all violations")
    
    class Config:
        json_schema_extra = {
            "example": {
                "contract_name": "sample-contract.pdf",
                "regulation_file": "data/regulations/li_2204.pdf",
                "analysis_timestamp": "2025-09-29T10:40:00.123456",
                "total_prompts_sent": 25,
                "successful_responses": 24,
                "failed_responses": 1,
                "potential_issues_found": 15,
                "violations": []
            }
        }


class ActiveAnalysis(BaseModel):
    """Model for active analysis summary."""
    analysis_id: str = Field(..., description="Analysis identifier")
    contract_name: str = Field(..., description="Contract filename")
    status: AnalysisStatus = Field(..., description="Current status")
    started_at: datetime = Field(..., description="Start timestamp")
    progress: str = Field(..., description="Current progress")


class ActiveAnalysesResponse(BaseModel):
    """Response model for active analyses list."""
    active_analyses: List[ActiveAnalysis] = Field(..., description="List of active analyses")
    total_active: int = Field(..., description="Total number of active analyses")
    
    class Config:
        json_schema_extra = {
            "example": {
                "active_analyses": [
                    {
                        "analysis_id": "987e6543-e21b-43d2-a567-426614174111",
                        "contract_name": "contract1.pdf",
                        "status": "running",
                        "started_at": "2025-09-29T10:35:00.123456",
                        "progress": "Processing contract nodes..."
                    }
                ],
                "total_active": 1
            }
        }


# Base Response Models
class BaseResponse(BaseModel):
    """Base response model with common fields."""
    success: bool = Field(..., description="Indicates if the operation was successful")
    message: str = Field(..., description="Human-readable message about the operation")
    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")


class ErrorResponse(BaseModel):
    """Standard error response model."""
    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Specific error code")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "detail": "File not found",
                "error_code": "FILE_NOT_FOUND",
                "timestamp": "2025-09-29T10:30:00.123456"
            }
        }


# Regulation Management Models
class RegulationInfo(BaseModel):
    """Information about a regulation document."""
    id: str = Field(..., description="Regulation identifier")
    title: str = Field(..., description="Regulation title")
    category: str = Field(..., description="Regulation category")
    description: Optional[str] = Field(None, description="Regulation description")
    version: Optional[str] = Field(None, description="Regulation version")
    effective_date: Optional[datetime] = Field(None, description="When the regulation became effective")
    file_path: str = Field(..., description="Path to the regulation file")
    last_updated: datetime = Field(..., description="When the regulation was last updated")
    document_count: int = Field(..., description="Number of indexed documents")
    is_indexed: bool = Field(..., description="Whether the regulation is currently indexed")


class RegulationListResponse(BaseResponse):
    """Response model for listing regulations."""
    regulations: List[RegulationInfo] = Field(..., description="List of available regulations")
    total_count: int = Field(..., description="Total number of regulations")


class RegulationRebuildResponse(BaseResponse):
    """Response model for regulation rebuild operations."""
    rebuilt_regulations: List[str] = Field(..., description="List of rebuilt regulation IDs")
    total_processed: int = Field(..., description="Total number of regulations processed")
    processing_time: float = Field(..., description="Time taken to rebuild in seconds")


class RegulationStatusResponse(BaseResponse):
    """Response model for regulation system status."""
    total_regulations: int = Field(..., description="Total number of regulations")
    indexed_regulations: int = Field(..., description="Number of indexed regulations")
    storage_type: str = Field(..., description="Type of vector storage being used")
    storage_path: Optional[str] = Field(None, description="Path to storage directory")