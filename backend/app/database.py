"""
Database connection and session management using SQLAlchemy 2.0 with async support.

This module provides the database engine, session factory, and base class
for all ORM models, along with dependency injection helpers for FastAPI routes.
"""

from typing import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

# Get application settings
settings = get_settings()

# SQLAlchemy 2.0 naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """
    Base class for all ORM models.
    
    Uses SQLAlchemy 2.0 declarative base with custom metadata
    for consistent constraint naming conventions.
    """
    metadata = metadata


# Create async engine with connection pooling
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,  # Log SQL queries in development
    pool_size=20,  # Maximum number of persistent connections
    max_overflow=0,  # No additional connections beyond pool_size
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    future=True,  # Use SQLAlchemy 2.0 future mode
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that provides a database session to FastAPI routes.
    
    This function creates a new SQLAlchemy async session for each request,
    yields it to the route handler, and ensures proper cleanup after the request.
    
    Usage:
        @app.get("/example")
        async def example_route(db: AsyncSession = Depends(get_db)):
            # Use db session here
            pass
    
    Yields:
        AsyncSession: SQLAlchemy async database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize the database by creating all tables.
    
    This function should be called during application startup to ensure
    all database tables are created. In production, use Alembic migrations instead.
    
    Note:
        This is primarily for development and testing. Use Alembic for production.
    """
    async with engine.begin() as conn:
        # Import all models here to ensure they're registered with Base.metadata
        from app import models  # noqa: F401
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections and dispose of the connection pool.
    
    This function should be called during application shutdown to ensure
    all database connections are properly closed and resources are released.
    """
    await engine.dispose()


async def check_db_connection() -> bool:
    """
    Check if database connection is healthy.
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.commit()
        return True
    except Exception:
        return False

