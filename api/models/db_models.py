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