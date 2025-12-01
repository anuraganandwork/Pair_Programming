"""
Main FastAPI application entry point.

This module initializes the FastAPI application, configures middleware,
sets up lifecycle events, and includes all API routers with comprehensive
production-ready features.
"""

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Callable

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.database import AsyncSessionLocal, check_db_connection, close_db
from app.services.code_sync_service import get_code_sync_service

# Get application settings
settings = get_settings()


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Reduce noise from verbose libraries
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add unique request ID to each request.
    
    Adds X-Request-ID header to responses and makes it available in logs.
    Useful for tracing requests across distributed systems.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and add request ID.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response with X-Request-ID header
        """
        # Generate or use existing request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Store in request state for access in routes
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track request processing time.
    
    Adds X-Process-Time header with duration in seconds.
    Logs slow requests for performance monitoring.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and track timing.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response with X-Process-Time header
        """
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        process_time = time.time() - start_time
        
        # Add to response headers
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log slow requests (> 1 second)
        if process_time > 1.0:
            logger.warning(
                f"Slow request: {request.method} {request.url.path} "
                f"took {process_time:.2f}s"
            )
        
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add unique request ID to each request.
    
    Adds X-Request-ID header to responses and makes it available in logs.
    Useful for tracing requests across distributed systems.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add request ID.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response with X-Request-ID header
        """
        # Generate or use existing request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Store in request state for access in routes
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track request processing time.
    
    Adds X-Process-Time header with duration in seconds.
    Logs slow requests for performance monitoring.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and track timing.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response with X-Process-Time header
        """
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        process_time = time.time() - start_time
        
        # Add to response headers
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log slow requests (> 1 second)
        if process_time > 1.0:
            logger.warning(
                f"Slow request: {request.method} {request.url.path} "
                f"took {process_time:.2f}s"
            )
        
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for application startup and shutdown events.
    
    Manages the complete lifecycle of the application including database
    connections, background tasks, and cleanup operations.
    
    Startup Tasks:
        1. Verify database connection
        2. Check migrations are up to date
        3. Initialize code sync service cache
        4. Start background sync task
        5. Log startup metrics
    
    Shutdown Tasks:
        1. Stop background tasks gracefully
        2. Force final database sync
        3. Close database connections
        4. Log shutdown metrics
    
    Args:
        app: FastAPI application instance
        
    Yields:
        None: Control to the application during its lifetime
    """
    # STARTUP
    startup_time = time.time()
    logger.info("=" * 70)
    logger.info(f"Starting Pair Programming API v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info("=" * 70)
    
    # 1. Check database connection
    logger.info("Checking database connection...")
    db_connected = await check_db_connection()
    if db_connected:
        logger.info("✓ Database connection established")
    else:
        logger.error("✗ Failed to connect to database")
        # Continue anyway - app can run with degraded functionality
    
    # 2. NOTE: Database migrations managed by Alembic
    # In production, run 'alembic upgrade head' before starting app
    # This ensures schema is up to date
    logger.info("NOTE: Database schema managed by Alembic migrations")
    logger.info("Run 'alembic upgrade head' to update schema")
    
    # 3. Initialize code sync service
    logger.info("Initializing code synchronization service...")
    try:
        sync_service = get_code_sync_service()
        
        # Load active rooms into cache
        async with AsyncSessionLocal() as db:
            await sync_service.initialize(db)
        
        logger.info("✓ Code sync service initialized")
        
        # 4. Start background sync task
        await sync_service.start_background_sync(AsyncSessionLocal)
        logger.info(
            f"✓ Background sync started (interval: "
            f"{sync_service._db_sync_interval}s)"
        )
        
    except Exception as e:
        logger.error(f"✗ Error initializing code sync service: {e}", exc_info=True)
        # Continue - app can still function
    
    # 5. Log startup completion
    startup_duration = time.time() - startup_time
    logger.info("=" * 70)
    logger.info(f"Application startup complete in {startup_duration:.2f}s")
    logger.info(f"API Documentation: http://localhost:8000/docs")
    logger.info(f"Health Check: http://localhost:8000/health")
    logger.info("=" * 70)
    
    # Application is running
    yield
    
    # SHUTDOWN
    shutdown_time = time.time()
    logger.info("=" * 70)
    logger.info("Shutting down application...")
    logger.info("=" * 70)
    
    # 1. Stop code sync service
    logger.info("Stopping code sync service...")
    try:
        sync_service = get_code_sync_service()
        
        # 2. Force final sync to database
        logger.info("Performing final sync to database...")
        async with AsyncSessionLocal() as db:
            synced = await sync_service.sync_to_database(db)
            logger.info(f"✓ Final sync complete: {synced} rooms saved")
        
        # Stop background task
        await sync_service.stop_background_sync()
        logger.info("✓ Background sync stopped")
        
    except Exception as e:
        logger.error(f"✗ Error during sync service shutdown: {e}", exc_info=True)
    
    # 3. Close database connections
    logger.info("Closing database connections...")
    try:
        await close_db()
        logger.info("✓ Database connections closed")
    except Exception as e:
        logger.error(f"✗ Error closing database: {e}", exc_info=True)
    
    # 4. Log shutdown completion
    shutdown_duration = time.time() - shutdown_time
    logger.info("=" * 70)
    logger.info(f"Application shutdown complete in {shutdown_duration:.2f}s")
    logger.info("=" * 70)


# Initialize FastAPI with comprehensive configuration
app = FastAPI(
    title="Pair Programming API",
    version="1.0.0",
    description="""
    # Real-Time Collaborative Coding Platform
    
    A production-ready API for pair programming with WebSocket support,
    real-time code synchronization, and AI-powered autocomplete.
    
    ## Features
    
    - 🚀 **Real-time Collaboration**: WebSocket-based code synchronization
    - 💾 **Smart Caching**: High-performance in-memory cache with background syncing
    - 🤖 **Code Autocomplete**: AI-powered code suggestions
    - 📊 **Monitoring**: Built-in health checks and statistics
    - 🔒 **Production-Ready**: Comprehensive error handling and logging
    
    ## Authentication
    
    Currently no authentication required (MVP).
    Future: Add JWT token-based authentication.
    
    ## Rate Limiting
    
    Future enhancement: Add rate limiting per IP/user.
    
    ## Support
    
    - Documentation: `/docs` (Swagger UI)
    - Alternative Docs: `/redoc`
    - Health Check: `/health`
    - Statistics: `/stats`
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    debug=settings.debug,
    # OpenAPI configuration
    openapi_tags=[
        {
            "name": "Root",
            "description": "Root endpoint with API information"
        },
        {
            "name": "Health",
            "description": "Health check and readiness endpoints"
        },
        {
            "name": "Monitoring",
            "description": "Application statistics and metrics"
        },
        {
            "name": "Rooms",
            "description": "Room management operations (CRUD)"
        },
        {
            "name": "Autocomplete",
            "description": "Code completion and suggestions"
        },
        {
            "name": "WebSocket",
            "description": "Real-time collaboration via WebSocket"
        },
    ],
)


# 1. CORS Middleware - Must be first for proper header handling
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)

# 2. Request ID Middleware - Add unique ID to each request
app.add_middleware(RequestIDMiddleware)

# 3. Timing Middleware - Track request processing time
app.add_middleware(TimingMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTPException with proper logging and response format.
    
    Logs the error with request context and returns a JSON response
    with consistent error format.
    
    Args:
        request: The request that caused the error
        exc: The HTTPException that was raised
        
    Returns:
        JSONResponse: Formatted error response
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.warning(
        f"HTTP {exc.status_code}: {exc.detail} "
        f"[{request.method} {request.url.path}] "
        f"[Request ID: {request_id}]"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "status_code": exc.status_code,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors with detailed error messages.
    
    Args:
        request: The request that caused the error
        exc: The validation error
        
    Returns:
        JSONResponse: Formatted validation error response
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.warning(
        f"Validation error: {exc.errors()} "
        f"[{request.method} {request.url.path}] "
        f"[Request ID: {request_id}]"
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "message": "Validation error",
                "status_code": 422,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions with full logging.
    
    Logs the full stack trace for debugging but returns a generic
    error message to avoid exposing internal implementation details.
    
    Args:
        request: The request that caused the error
        exc: The unexpected exception
        
    Returns:
        JSONResponse: Generic error response
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error(
        f"Unexpected error: {str(exc)} "
        f"[{request.method} {request.url.path}] "
        f"[Request ID: {request_id}]",
        exc_info=True  # Include full stack trace
    )
    
    # In production, don't expose internal error details
    error_message = "An internal server error occurred"
    if settings.debug:
        error_message = f"{type(exc).__name__}: {str(exc)}"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": error_message,
                "status_code": 500,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        },
    )


@app.get(
    "/health",
    tags=["Health"],
    summary="Basic health check",
    description="Quick health check for load balancers and monitoring systems",
)
async def health_check() -> JSONResponse:
    """
    Basic health check endpoint.
    
    Performs a quick check of database connectivity. Returns 200 if healthy,
    503 if degraded. Suitable for load balancer health checks.
    
    Returns:
        JSONResponse: Health status with status code
        
    Response (200 OK):
        ```json
        {
            "status": "healthy",
            "timestamp": "2025-11-30T12:00:00Z",
            "environment": "development",
            "database": "connected"
        }
        ```
    
    Response (503 Service Unavailable):
        ```json
        {
            "status": "degraded",
            "timestamp": "2025-11-30T12:00:00Z",
            "environment": "development",
            "database": "disconnected"
        }
        ```
    """
    db_healthy = await check_db_connection()
    
    health_status = {
        "status": "healthy" if db_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment,
        "database": "connected" if db_healthy else "disconnected",
    }
    
    status_code = (
        status.HTTP_200_OK
        if db_healthy
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    
    return JSONResponse(content=health_status, status_code=status_code)


@app.get(
    "/health/ready",
    tags=["Health"],
    summary="Readiness check",
    description="Comprehensive readiness check for Kubernetes and orchestration systems",
)
async def readiness_check() -> JSONResponse:
    """
    Readiness check endpoint for orchestration systems.
    
    Performs comprehensive checks to determine if the application is ready
    to serve traffic. Checks database, cache, and background tasks.
    
    Suitable for Kubernetes readiness probes.
    
    Returns:
        JSONResponse: Readiness status with status code
        
    Response (200 OK):
        ```json
        {
            "ready": true,
            "timestamp": "2025-11-30T12:00:00Z",
            "checks": {
                "database": "connected",
                "cache": "initialized",
                "background_tasks": "running"
            }
        }
        ```
    
    Response (503 Service Unavailable):
        ```json
        {
            "ready": false,
            "timestamp": "2025-11-30T12:00:00Z",
            "checks": {
                "database": "disconnected",
                "cache": "initialized",
                "background_tasks": "running"
            }
        }
        ```
    """
    checks = {}
    all_ready = True
    
    # Check database
    db_healthy = await check_db_connection()
    checks["database"] = "connected" if db_healthy else "disconnected"
    if not db_healthy:
        all_ready = False
    
    # Check code sync service
    try:
        sync_service = get_code_sync_service()
        stats = sync_service.get_cache_stats()
        checks["cache"] = "initialized"
        checks["cache_size"] = stats["cache_size"]
        
        # Check if background task is running
        if sync_service._background_task and not sync_service._background_task.done():
            checks["background_tasks"] = "running"
        else:
            checks["background_tasks"] = "stopped"
            all_ready = False
            
    except Exception as e:
        logger.error(f"Error checking sync service: {e}")
        checks["cache"] = "error"
        all_ready = False
    
    response_data = {
        "ready": all_ready,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }
    
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(content=response_data, status_code=status_code)


@app.get(
    "/",
    tags=["Root"],
    summary="API information",
    description="Root endpoint providing API information and navigation links",
)
async def root() -> dict:
    """
    Root endpoint with API information and navigation.
    
    Provides an overview of the API, version information, and links
    to documentation and health check endpoints.
    
    Returns:
        dict: API information and navigation links
        
    Example Response:
        ```json
        {
            "name": "Pair Programming API",
            "version": "1.0.0",
            "environment": "development",
            "endpoints": {
                "documentation": "/docs",
                "health": "/health",
                "readiness": "/health/ready",
                "statistics": "/stats"
            },
            "features": ["real-time collaboration", "code autocomplete", "room management"]
        }
        ```
    """
    return {
        "name": "Pair Programming API",
        "version": "1.0.0",
        "environment": settings.environment,
        "description": "Real-time collaborative coding platform",
        "endpoints": {
            "documentation": "/docs",
            "alternative_docs": "/redoc",
            "openapi_spec": "/openapi.json",
            "health": "/health",
            "readiness": "/health/ready",
            "statistics": "/stats",
        },
        "features": [
            "real-time collaboration",
            "code autocomplete",
            "room management",
            "websocket support",
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get(
    "/stats",
    tags=["Monitoring"],
    summary="Application statistics",
    description="Get real-time application metrics for monitoring and debugging",
)
async def get_stats() -> dict:
    """
    Get comprehensive application statistics.
    
    Provides real-time metrics about cache performance, WebSocket connections,
    and system health. Useful for monitoring dashboards and debugging.
    
    Returns:
        dict: Application statistics including:
            - cache: Cache performance metrics
            - websocket: Active connections and rooms
            - environment: Current environment
            - timestamp: Current server time
            
    Example Response:
        ```json
        {
            "cache": {
                "cache_size": 10,
                "dirty_rooms": 2,
                "hit_rate": 87.5,
                "total_hits": 245,
                "total_misses": 35,
                "total_updates": 180,
                "total_syncs": 45,
                "total_conflicts": 0,
                "total_errors": 0,
                "sync_interval_seconds": 2
            },
            "websocket": {
                "active_rooms": 5,
                "total_connections": 12
            },
            "environment": "development",
            "timestamp": "2025-11-30T12:00:00Z"
        }
        ```
    """
    # Get cache statistics
    sync_service = get_code_sync_service()
    cache_stats = sync_service.get_cache_stats()
    
    # Get WebSocket connection statistics
    from app.routers.websocket import manager
    
    total_connections = sum(
        len(connections)
        for connections in manager.active_connections.values()
    )
    
    # Get detailed room info
    room_details = []
    for room_id in list(manager.active_connections.keys()):
        room_info = await sync_service.get_room_info(room_id)
        if room_info:
            room_details.append(room_info)
    
    return {
        "cache": cache_stats,
        "websocket": {
            "active_rooms": len(manager.active_connections),
            "total_connections": total_connections,
            "rooms": room_details[:5],  # Top 5 rooms
        },
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
    }


# Import routers
from app.routers import autocomplete, rooms, websocket

# Include routers with consistent prefixes
# Note: Routers define their own prefixes, so we don't add them here
app.include_router(rooms.router)
app.include_router(autocomplete.router)
app.include_router(websocket.router)

logger.info("All routers registered successfully")


if __name__ == "__main__":
    """
    Direct execution entry point for development.
    
    For production, use:
        uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    
    Or with gunicorn:
        gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
    """
    import uvicorn
    
    logger.info("Starting application via direct execution")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level="debug" if settings.debug else "info",
        access_log=True,
    )

