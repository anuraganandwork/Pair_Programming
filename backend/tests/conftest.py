"""
Pytest configuration and fixtures for testing.

This module provides shared fixtures for all test modules, including:
    - Test application setup
    - Test database with migrations
    - Test client for API requests
    - Sample data fixtures
"""

import asyncio
import os
from typing import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.database import AsyncSessionLocal, Base, get_db
from app.main import app
from app.models import Room
from app.services.code_sync_service import CodeSyncService, get_code_sync_service

# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/pairprogramming_test"
)

# Sync version for migrations
TEST_DATABASE_URL_SYNC = TEST_DATABASE_URL.replace("+asyncpg", "")


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create an event loop for the test session.
    
    This is required for pytest-asyncio to work properly with session-scoped
    async fixtures.
    
    Yields:
        asyncio.AbstractEventLoop: Event loop for the test session
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# SETTINGS FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """
    Create test settings with test database URL.
    
    Returns:
        Settings: Test configuration settings
    """
    return Settings(
        DATABASE_URL=TEST_DATABASE_URL,
        ENVIRONMENT="test",
        CORS_ORIGINS=["http://localhost:3000"],
        WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS=10,
        WEBSOCKET_MAX_CONNECTIONS_PER_ROOM=5,
        ROOM_CLEANUP_MAX_AGE_HOURS=1,
        ROOM_CLEANUP_INTERVAL_SECONDS=60,
    )


@pytest.fixture(scope="function")
def override_settings(test_settings: Settings):
    """
    Override application settings with test settings.
    
    Args:
        test_settings: Test configuration
        
    Yields:
        Settings: Test settings
    """
    # Override the get_settings function
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield test_settings
    # Clear overrides after test
    app.dependency_overrides.clear()


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """
    Create a test database engine for the session.
    
    Creates the test database if it doesn't exist, then provides
    an async engine for test operations.
    
    Yields:
        AsyncEngine: SQLAlchemy async engine for test database
    """
    # Create test database if it doesn't exist
    sync_engine = create_engine(TEST_DATABASE_URL_SYNC.rsplit("/", 1)[0] + "/postgres")
    
    with sync_engine.connect() as conn:
        conn.execute(text("COMMIT"))  # Close any open transaction
        # Check if database exists
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'pairprogramming_test'")
        )
        if not result.scalar():
            conn.execute(text("CREATE DATABASE pairprogramming_test"))
    
    sync_engine.dispose()
    
    # Create async engine
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean database session for each test.
    
    Creates a new session, yields it for the test, then rolls back
    any changes and closes the session.
    
    Args:
        test_engine: SQLAlchemy async engine
        
    Yields:
        AsyncSession: Database session for testing
    """
    # Create session factory
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        # Start a transaction
        async with session.begin():
            yield session
            # Rollback after test
            await session.rollback()


@pytest.fixture(scope="function")
def override_get_db(db_session: AsyncSession):
    """
    Override the get_db dependency with test database session.
    
    Args:
        db_session: Test database session
        
    Yields:
        AsyncSession: Test database session
    """
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session
    
    app.dependency_overrides[get_db] = _override_get_db
    yield db_session
    app.dependency_overrides.clear()


# ============================================================================
# APPLICATION FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def test_app(override_settings, override_get_db):
    """
    Provide the FastAPI test application with overridden dependencies.
    
    Args:
        override_settings: Test settings fixture
        override_get_db: Test database fixture
        
    Returns:
        FastAPI: Configured test application
    """
    return app


@pytest_asyncio.fixture(scope="function")
async def client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP client for testing API endpoints.
    
    Args:
        test_app: FastAPI test application
        
    Yields:
        AsyncClient: HTTPX async client for making requests
    """
    async with AsyncClient(app=test_app, base_url="http://test") as ac:
        yield ac


# ============================================================================
# SERVICE FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def test_code_sync_service():
    """
    Provide a fresh CodeSyncService instance for testing.
    
    Returns:
        CodeSyncService: Fresh service instance with clean cache
    """
    service = CodeSyncService(db_sync_interval=1)
    yield service
    # Clear cache after test
    service._cache.clear()
    service._dirty_rooms.clear()


# ============================================================================
# DATA FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def sample_room(db_session: AsyncSession) -> Room:
    """
    Create a sample room for testing.
    
    Creates a room with default values and commits it to the database.
    
    Args:
        db_session: Database session
        
    Returns:
        Room: Created room instance
    """
    room = Room(
        id=uuid4(),
        code="print('Hello, World!')",
        language="python",
    )
    db_session.add(room)
    await db_session.commit()
    await db_session.refresh(room)
    return room


@pytest_asyncio.fixture
async def sample_room_with_code(db_session: AsyncSession) -> Room:
    """
    Create a sample room with substantial code for testing.
    
    Args:
        db_session: Database session
        
    Returns:
        Room: Created room instance with code
    """
    code = """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

def main():
    for i in range(10):
        print(f"fibonacci({i}) = {fibonacci(i)}")

if __name__ == "__main__":
    main()
"""
    room = Room(
        id=uuid4(),
        code=code,
        language="python",
    )
    db_session.add(room)
    await db_session.commit()
    await db_session.refresh(room)
    return room


@pytest_asyncio.fixture
async def multiple_rooms(db_session: AsyncSession) -> list[Room]:
    """
    Create multiple sample rooms for testing.
    
    Args:
        db_session: Database session
        
    Returns:
        list[Room]: List of created room instances
    """
    rooms = []
    languages = ["python", "javascript", "typescript", "java"]
    
    for i, lang in enumerate(languages):
        room = Room(
            id=uuid4(),
            code=f"// Sample code for {lang}",
            language=lang,
        )
        db_session.add(room)
        rooms.append(room)
    
    await db_session.commit()
    
    for room in rooms:
        await db_session.refresh(room)
    
    return rooms


# ============================================================================
# WEBSOCKET FIXTURES
# ============================================================================

@pytest.fixture
def websocket_url():
    """
    Provide base WebSocket URL for testing.
    
    Returns:
        str: WebSocket base URL
    """
    return "ws://test/ws"


# ============================================================================
# HELPER FIXTURES
# ============================================================================

@pytest.fixture
def valid_room_data():
    """
    Provide valid room creation data.
    
    Returns:
        dict: Valid room data
    """
    return {
        "language": "python",
        "code": "print('Test')"
    }


@pytest.fixture
def valid_code_update():
    """
    Provide valid code update data.
    
    Returns:
        dict: Valid code update data
    """
    return {
        "code": "def test():\n    pass",
        "user_id": "test_user_123"
    }


@pytest.fixture
def valid_autocomplete_request():
    """
    Provide valid autocomplete request data.
    
    Returns:
        dict: Valid autocomplete request
    """
    return {
        "code": "def ",
        "cursor_position": 4,
        "language": "python"
    }


@pytest.fixture
def invalid_uuid():
    """
    Provide an invalid UUID string for testing error cases.
    
    Returns:
        str: Invalid UUID string
    """
    return "not-a-valid-uuid"


@pytest.fixture
def nonexistent_uuid():
    """
    Provide a valid but non-existent UUID for testing 404 cases.
    
    Returns:
        str: Valid UUID that doesn't exist in database
    """
    return str(uuid4())

