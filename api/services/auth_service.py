# api/services/auth_service.py
"""
Authentication Service
=====================

Handles user authentication, JWT token management, and security operations.

Note: Install required dependencies:
pip install python-jose[cryptography] passlib[bcrypt] python-multipart
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

try:
    from jose import JWTError, jwt
    from passlib.context import CryptContext
    JWT_AVAILABLE = True
except ImportError:
    # Fallback for development without JWT dependencies
    JWT_AVAILABLE = False
    JWTError = Exception
    
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_

from api.models.auth_models import User, RefreshToken, APIKey, AuditLog
from config.settings import settings


class AuthService:
    """Authentication service for user management and JWT operations."""
    
    def __init__(self):
        if not JWT_AVAILABLE:
            raise ImportError(
                "JWT dependencies not installed. Run: "
                "pip install python-jose[cryptography] passlib[bcrypt] python-multipart"
            )
            
        # Password hashing
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # JWT settings
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        
        # Account lockout settings
        self.max_login_attempts = settings.MAX_LOGIN_ATTEMPTS
        self.lockout_duration_minutes = settings.LOCKOUT_DURATION_MINUTES
    
    # Password operations
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        return self.pwd_context.hash(password)
    
    def validate_password_strength(self, password: str) -> Tuple[bool, str]:
        """
        Validate password strength.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"
        
        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"
        
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"
        
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            return False, "Password must contain at least one special character"
        
        return True, ""
    
    # User authentication
    async def authenticate_user(
        self, 
        session: AsyncSession, 
        username: str, 
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[User]:
        """
        Authenticate a user with username/password.
        
        Returns:
            User object if authentication successful, None otherwise
        """
        try:
            # Get user
            query = select(User).where(
                (User.username == username) | (User.email == username)
            )
            result = await session.execute(query)
            user = result.scalar_one_or_none()
            
            # Check if user exists
            if not user:
                await self._log_auth_event(
                    session, None, "login_failed", 
                    f"User not found: {username}",
                    ip_address, user_agent, success=False
                )
                return None
            
            # Check if account is locked
            if await self._is_account_locked(user):
                await self._log_auth_event(
                    session, user.id, "login_failed", 
                    "Account locked due to too many failed attempts",
                    ip_address, user_agent, success=False
                )
                return None
            
            # Verify password
            if not self.verify_password(password, user.hashed_password):
                await self._handle_failed_login(session, user, ip_address, user_agent)
                return None
            
            # Reset failed attempts and update last login
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = datetime.utcnow()
            
            await session.commit()
            
            # Log successful login
            await self._log_auth_event(
                session, user.id, "login_success", 
                f"User logged in: {username}",
                ip_address, user_agent, success=True
            )
            
            return user
            
        except Exception as e:
            await self._log_auth_event(
                session, None, "login_error", 
                f"Authentication error: {str(e)}",
                ip_address, user_agent, success=False
            )
            return None
    
    # JWT token operations
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire, "type": "access"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    async def create_refresh_token(
        self, 
        session: AsyncSession, 
        user_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """Create and store a refresh token."""
        # Generate random token
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Create refresh token record
        refresh_token = RefreshToken(
            token_hash=token_hash,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(days=self.refresh_token_expire_days),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        session.add(refresh_token)
        await session.commit()
        
        return token
    
    def decode_access_token(self, token: str) -> Optional[dict]:
        """Decode and validate a JWT access token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Check token type
            if payload.get("type") != "access":
                return None
            
            return payload
        except JWTError:
            return None
    
    async def refresh_access_token(
        self, 
        session: AsyncSession, 
        refresh_token: str
    ) -> Optional[Tuple[str, str]]:
        """
        Refresh access token using refresh token.
        
        Returns:
            Tuple of (new_access_token, new_refresh_token) if successful
        """
        try:
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            
            # Find refresh token
            query = select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked == False,
                RefreshToken.expires_at > datetime.utcnow()
            )
            result = await session.execute(query)
            token_record = result.scalar_one_or_none()
            
            if not token_record:
                return None
            
            # Get user
            user_query = select(User).where(User.id == token_record.user_id)
            user_result = await session.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user or not user.is_active:
                return None
            
            # Revoke old token
            token_record.is_revoked = True
            
            # Create new tokens
            new_access_token = self.create_access_token({
                "sub": str(user.id),
                "username": user.username,
                "role": user.role
            })
            
            if user.id is not None:  # Type guard for user.id
                new_refresh_token = await self.create_refresh_token(
                    session, user.id, 
                    token_record.ip_address, 
                    token_record.user_agent
                )
            
            await session.commit()
            
            return new_access_token, new_refresh_token
            
        except Exception:
            return None
    
    # API Key operations
    def generate_api_key(self) -> Tuple[str, str, str]:
        """
        Generate a new API key.
        
        Returns:
            Tuple of (full_key, key_hash, key_prefix)
        """
        # Generate key: prefix + random part
        prefix = "cmai_"
        random_part = secrets.token_urlsafe(32)
        full_key = f"{prefix}{random_part}"
        
        # Hash the key for storage
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        
        return full_key, key_hash, prefix + random_part[:8]
    
    async def validate_api_key(
        self, 
        session: AsyncSession, 
        api_key: str
    ) -> Optional[User]:
        """Validate an API key and return the associated user."""
        try:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            
            # Find API key - simpler query for now
            query = select(APIKey).where(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True
            )
            
            result = await session.execute(query)
            api_key_record = result.scalar_one_or_none()
            
            if not api_key_record:
                return None
            
            # Check expiration manually
            if (api_key_record.expires_at is not None and 
                api_key_record.expires_at <= datetime.utcnow()):
                return None
            
            # Get user
            user_query = select(User).where(
                User.id == api_key_record.user_id,
                User.is_active == True
            )
            user_result = await session.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                return None
            
            # Update last used timestamp
            api_key_record.last_used = datetime.utcnow()
            await session.commit()
            
            return user
            
        except Exception:
            return None
    
    # Helper methods
    async def _is_account_locked(self, user: User) -> bool:
        """Check if user account is locked."""
        if user.locked_until and user.locked_until > datetime.utcnow():
            return True
        return False
    
    async def _handle_failed_login(
        self, 
        session: AsyncSession, 
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Handle failed login attempt."""
        user.failed_login_attempts += 1
        
        # Lock account if too many attempts
        if user.failed_login_attempts >= self.max_login_attempts:
            user.locked_until = datetime.utcnow() + timedelta(
                minutes=self.lockout_duration_minutes
            )
            
            await self._log_auth_event(
                session, user.id, "account_locked", 
                f"Account locked after {self.max_login_attempts} failed attempts",
                ip_address, user_agent, success=False
            )
        else:
            await self._log_auth_event(
                session, user.id, "login_failed", 
                f"Invalid password (attempt {user.failed_login_attempts})",
                ip_address, user_agent, success=False
            )
        
        await session.commit()
    
    async def _log_auth_event(
        self,
        session: AsyncSession,
        user_id: Optional[int],
        event_type: str,
        description: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        details: Optional[dict] = None
    ):
        """Log authentication event for audit purposes."""
        audit_log = AuditLog(
            event_type=event_type,
            event_description=description,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            details=details
        )
        
        session.add(audit_log)
        await session.commit()


# Global auth service instance
auth_service = AuthService()