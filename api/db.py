# api/db.py
"""
Database connection and session management.
"""
# --- Corrected Imports ---
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession # Use SQLAlchemy's async engine creation
# --- End Corrected Imports ---
from typing import AsyncGenerator

from config import settings # Import settings correctly

# Create the async engine based on the DATABASE_URL from settings
# Use create_async_engine directly
database_url = settings.DATABASE_URL
if not database_url:
    raise ValueError("DATABASE_URL is not set. Please configure settings.DATABASE_URL with a valid SQLAlchemy URL.")

engine = create_async_engine(
    database_url,
    echo=getattr(settings, "DB_ECHO", False) # Log SQL queries if DB_ECHO is True
)

# Create an async session factory using the correct signature
AsyncSessionLocal = async_sessionmaker(
    bind=engine, # Use 'bind' argument
    expire_on_commit=False,
    class_=AsyncSession
)

async def init_db() -> None:
    """
    Initialize the database and create all tables.
    This is called on application startup.
    """
    # Import SQLModel here only when needed to avoid potential circular imports
    # if other modules import db.py early
    from sqlmodel import SQLModel
    async with engine.begin() as conn:
        # This command finds all classes that inherit from SQLModel
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get a database session.

    This will be injected into endpoint functions.
    It ensures that a session is created for each request
    and closed automatically when the request is finished.
    """
    async with AsyncSessionLocal() as session:
        yield session