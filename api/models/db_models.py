# api/models/db_models.py
"""
Database table models using SQLModel.
"""

import uuid
import datetime
from typing import Optional, Dict, Any
from sqlmodel import Field, SQLModel, JSON, Column
from api.models.schemas import AnalysisStatus

class Analysis(SQLModel, table=True):
    """
    Database model for an analysis task.
    This class defines the 'analysis' table structure.
    """
    __tablename__ = "analysis"
    
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
    results: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    report_paths: Optional[Dict[str, str]] = Field(default=None, sa_column=Column(JSON))
    
    error: Optional[str] = Field(default=None)