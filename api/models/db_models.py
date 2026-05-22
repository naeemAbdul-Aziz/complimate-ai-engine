# api/models/db_models.py
"""
Database table models using SQLModel.
"""

# --- Corrected Imports ---
import uuid
import datetime
from typing import Optional, Dict, Any
# Column might be re-exported by SQLModel, but JSON usually comes from sqlalchemy
from sqlmodel import Field, SQLModel, Column
from sqlalchemy import JSON # Import JSON from sqlalchemy explicitly
# --- End Corrected Imports ---

from api.models.schemas import AnalysisStatus

class UploadedFile(SQLModel, table=True):
    """Persistent uploaded file metadata.

    Provides durability for file references across process restarts and
    horizontal scaling (multiple API workers). In-memory FileService registry
    remains as a fast cache; DB is source of truth.
    """
    file_id: str = Field(primary_key=True, index=True)
    original_filename: str
    stored_filename: str
    file_path: str
    file_size: int
    content_type: Optional[str] = Field(default=None)
    uploaded_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, index=True)

class Analysis(SQLModel, table=True):
    """
    Database model for an analysis task.
    This class defines the 'analysis' table structure.
    """
    # Use UUID as the primary key
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)

    contract_name: str = Field(index=True)
    file_path: str

    # Use the AnalysisStatus enum for the status field
    status: AnalysisStatus = Field(default=AnalysisStatus.STARTED, index=True)
    progress: str = Field(default="Analysis started")

    started_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    completed_at: Optional[datetime.datetime] = Field(default=None)

    # Store complex Python objects (dicts) as JSON in the database
    # Use sa_column with the imported Column and JSON types
    results: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    report_paths: Optional[Dict[str, str]] = Field(default=None, sa_column=Column(JSON))

    error: Optional[str] = Field(default=None)


class RegulationDocument(SQLModel, table=True):
    """Tracks the lifecycle of each regulation PDF from upload to Pinecone indexing.

    This table is the V3 source of truth for regulation state, replacing the local
    regulations_metadata.json file. Each row corresponds to one PDF file.

    Status flow: PENDING → INDEXING → ACTIVE | ERROR | RETIRED
    """
    __tablename__ = "regulation_documents"

    id: Optional[int] = Field(default=None, primary_key=True)

    # File identity
    file_name: str = Field(index=True)
    title: str
    category: str = Field(default="petroleum")  # petroleum | mining | environmental | labor | general
    description: Optional[str] = Field(default=None)

    # Deduplication — SHA256 hash of the raw PDF bytes
    file_hash: str = Field(index=True)

    # Where the PDF lives (local path Phase 1, S3 key Phase 2)
    storage_path: str

    # Indexing state
    chunk_count: int = Field(default=0)
    status: str = Field(default="PENDING", index=True)  # PENDING | INDEXING | ACTIVE | ERROR | RETIRED
    pinecone_namespace: Optional[str] = Field(default=None)  # e.g. "doc_42" — unique per document
    error_message: Optional[str] = Field(default=None)

    # Timestamps
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    indexed_at: Optional[datetime.datetime] = Field(default=None)
    retired_at: Optional[datetime.datetime] = Field(default=None)