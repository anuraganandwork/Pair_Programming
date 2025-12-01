"""
Shared dependencies for FastAPI dependency injection.

This module provides reusable dependencies for routes including database
sessions, authentication, rate limiting, and common query parameters.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session to route handlers.
    
    This function creates a new SQLAlchemy async session for each request,
    yields it to the route handler, and ensures proper cleanup with error handling.
    
    Usage:
        ```python
        @router.get("/rooms/{room_id}")
        async def get_room(
            room_id: UUID,
            db: AsyncSession = Depends(get_db)
        ):
            # Use db session here
            result = await db.execute(select(Room).where(Room.id == room_id))
            return result.scalar_one_or_none()
        ```
    
    Yields:
        AsyncSession: SQLAlchemy async database session
        
    Raises:
        Exception: Any database errors are propagated to FastAPI's exception handlers
    """
    session: AsyncSession = AsyncSessionLocal()
    try:
        yield session
        # Commit any pending transactions on successful completion
        await session.commit()
    except Exception:
        # Rollback on any exception
        await session.rollback()
        raise
    finally:
        # Always close the session
        await session.close()


# Additional dependencies can be added here as needed:
# - Authentication dependencies
# - Rate limiting
# - Pagination parameters
# - Validation helpers

