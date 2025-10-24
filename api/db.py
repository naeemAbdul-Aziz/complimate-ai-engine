# api/db.py
"""
Database connection and session management.
"""

from sqlmodel import SQLModel, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from config import settings

# Create the async engine based on the DATABASE_URL from settings
# The URL format determines the driver (e.g., sqlite+aiosqlite or postgresql+asyncpg)
engine = AsyncEngine(create_engine(
    settings.DATABASE_URL, 
    echo=settings.DB_ECHO,  # Log SQL queries if DB_ECHO is True
    future=True
))

# Create an async session factory
AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def init_db():
    """
    Initialize the database and create all tables.
    This is called on application startup.
    """
    async with engine.begin() as conn:
        # This command finds all classes that inherit from SQLModel
        # and creates their corresponding tables in the database.
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    """
    FastAPI dependency to get a database session.
    
    This will be injected into endpoint functions.
    It ensures that a session is created for each request
    and closed automatically when the request is finished.
    """
    async with AsyncSessionLocal() as session:
        yield session