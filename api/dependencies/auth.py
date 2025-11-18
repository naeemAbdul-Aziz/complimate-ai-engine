# api/dependencies/auth.py
"""
Authentication Dependencies
==========================

FastAPI dependencies for JWT authentication and authorization.
"""

from typing import Optional, Annotated
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.db import get_session
from api.models.auth_models import User
from api.services.auth_service import auth_service


# Security scheme for JWT tokens
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    session: AsyncSession = Depends(get_session)
) -> User:
    """
    Get current authenticated user from JWT token or API key.
    
    Supports both:
    - Authorization: Bearer <jwt_token>
    - Authorization: Bearer <api_key>
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not credentials:
        raise credentials_exception
    
    token = credentials.credentials
    
    # Try JWT token first
    payload = auth_service.decode_access_token(token)
    if payload:
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
        # Get user from database
        query = select(User).where(User.id == int(user_id))
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if user is None or not user.is_active:
            raise credentials_exception
        
        # Log API access
        await auth_service._log_auth_event(
            session, user.id, "api_access",
            f"API access via JWT: {request.url.path}",
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            success=True
        )
        
        return user
    
    # Try API key
    user = await auth_service.validate_api_key(session, token)
    if user:
        # Log API access
        await auth_service._log_auth_event(
            session, user.id, "api_access",
            f"API access via API key: {request.url.path}",
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            success=True
        )
        return user
    
    raise credentials_exception


def require_role(*allowed_roles: str):
    """
    Dependency factory for role-based access control.
    
    Usage:
        @router.get("/admin")
        async def admin_endpoint(user: User = Depends(require_role("admin"))):
            pass
    """
    def role_dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return user
    
    return role_dependency


def require_active_user(user: User = Depends(get_current_user)) -> User:
    """Ensure user is active."""
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    return user


async def optional_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    session: AsyncSession = Depends(get_session)
) -> Optional[User]:
    """
    Optional authentication - returns None if no valid credentials.
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    if not credentials:
        return None
    
    try:
        # Use the same logic as get_current_user but don't raise exceptions
        token = credentials.credentials
        
        # Try JWT first
        payload = auth_service.decode_access_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                query = select(User).where(
                    User.id == int(user_id),
                    User.is_active == True
                )
                result = await session.execute(query)
                user = result.scalar_one_or_none()
                return user
        
        # Try API key
        return await auth_service.validate_api_key(session, token)
        
    except Exception:
        return None


# Pre-configured dependencies for common roles
require_admin = require_role("admin")
require_analyst = require_role("analyst", "admin")
require_user = require_role("user", "analyst", "admin")