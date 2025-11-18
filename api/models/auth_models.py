# api/models/auth_models.py
"""
Authentication and User Management Models
========================================

SQLModel definitions for user authentication, roles, and sessions.
"""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, DateTime, JSON


class User(SQLModel, table=True):
    """User model for authentication and authorization."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, min_length=3, max_length=50)
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str = Field(max_length=255)
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    role: str = Field(default="user", max_length=20)  # user, analyst, admin
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)
    last_login: Optional[datetime] = Field(default=None)
    
    # Profile information
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    organization: Optional[str] = Field(default=None, max_length=200)
    
    # Security settings
    failed_login_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = Field(default=None)
    password_changed_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    api_keys: list["APIKey"] = Relationship(back_populates="user")
    audit_logs: list["AuditLog"] = Relationship(back_populates="user")


class APIKey(SQLModel, table=True):
    """API Key model for service-to-service authentication."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)  # Human-readable name
    key_hash: str = Field(unique=True, index=True)  # Hashed API key
    key_prefix: str = Field(max_length=10)  # First 8 chars for identification
    
    # Foreign key
    user_id: int = Field(foreign_key="user.id")
    user: User = Relationship(back_populates="api_keys")
    
    # Permissions and limits
    scopes: str = Field(default="read")  # Comma-separated: read,write,admin
    rate_limit_per_hour: int = Field(default=1000)
    
    # Status and lifecycle
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)


class RefreshToken(SQLModel, table=True):
    """Refresh token model for JWT token rotation."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    
    # Token metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    is_revoked: bool = Field(default=False)
    
    # Device/session tracking
    user_agent: Optional[str] = Field(default=None, max_length=500)
    ip_address: Optional[str] = Field(default=None, max_length=45)
    device_fingerprint: Optional[str] = Field(default=None, max_length=100)


class AuditLog(SQLModel, table=True):
    """Audit log for security events and user actions."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Event details
    event_type: str = Field(max_length=50)  # login, logout, api_call, etc.
    event_description: str = Field(max_length=500)
    
    # User context
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional[User] = Relationship(back_populates="audit_logs")
    
    # Request context
    ip_address: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = Field(default=None, max_length=500)
    endpoint: Optional[str] = Field(default=None, max_length=200)
    method: Optional[str] = Field(default=None, max_length=10)
    
    # Additional data
    details: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Status
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None, max_length=1000)
    
    # Timestamp
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Pydantic models for API requests/responses
class UserBase(SQLModel):
    """Base user schema for API requests."""
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    organization: Optional[str] = Field(default=None, max_length=200)


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(min_length=8, max_length=100)
    role: Optional[str] = Field(default="user")


class UserUpdate(SQLModel):
    """User update schema."""
    email: Optional[str] = Field(default=None, max_length=255)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    organization: Optional[str] = Field(default=None, max_length=200)
    is_active: Optional[bool] = Field(default=None)


class UserResponse(UserBase):
    """User response schema."""
    id: int
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None


class LoginRequest(SQLModel):
    """Login request schema."""
    username: str
    password: str
    remember_me: bool = Field(default=False)


class TokenResponse(SQLModel):
    """Token response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class APIKeyCreate(SQLModel):
    """API key creation schema."""
    name: str = Field(max_length=100)
    scopes: Optional[str] = Field(default="read")
    expires_in_days: Optional[int] = Field(default=None, le=365)
    rate_limit_per_hour: Optional[int] = Field(default=1000)


class APIKeyResponse(SQLModel):
    """API key response schema."""
    id: int
    name: str
    key_prefix: str
    scopes: str
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    # Returned only at creation time; not persisted
    key: Optional[str] = None


class PasswordChangeRequest(SQLModel):
    """Password change request schema."""
    current_password: str
    new_password: str = Field(min_length=8, max_length=100)