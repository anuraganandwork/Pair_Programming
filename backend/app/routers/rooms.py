"""
Room management REST API endpoints.

This module provides HTTP endpoints for creating, retrieving, updating,
and deleting coding rooms in the pair programming application.
"""

import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas import CodeUpdate, RoomCreate, RoomResponse
from app.services.room_service import RoomService

# Configure logging
logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(
    prefix="/api/v1/rooms",
    tags=["Rooms"],
)


@router.post(
    "",
    response_model=Dict[str, str],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new coding room",
    description="Creates a new room with optional language and initial code. Returns the room ID.",
    responses={
        201: {
            "description": "Room created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "roomId": "550e8400-e29b-41d4-a716-446655440000"
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to create room due to database error"
                    }
                }
            }
        }
    }
)
async def create_room(
    room: RoomCreate = RoomCreate(),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Create a new coding room.
    
    Creates a new room with the specified language and optional initial code.
    If no parameters are provided, creates a Python room with empty code.
    
    Args:
        room: Room creation parameters (language and initial code)
        db: Database session (injected)
    
    Returns:
        Dict containing the new room's ID
        
    Example:
        ```
        POST /api/v1/rooms
        {
            "language": "javascript",
            "code": "console.log('Hello');"
        }
        
        Response (201):
        {
            "roomId": "550e8400-e29b-41d4-a716-446655440000"
        }
        ```
    """
    logger.info(f"Creating new room with language: {room.language}")
    
    try:
        new_room = await RoomService.create_room(
            db,
            language=room.language,
            initial_code=room.code
        )
        
        logger.info(f"Room created successfully: {new_room.id}")
        
        return {"roomId": str(new_room.id)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating room: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the room"
        )


@router.get(
    "/{room_id}",
    response_model=RoomResponse,
    status_code=status.HTTP_200_OK,
    summary="Get room by ID",
    description="Retrieves a room's details including code, language, and timestamps.",
    responses={
        200: {
            "description": "Room found",
            "content": {
                "application/json": {
                    "example": {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "code": "def hello():\n    print('Hello, World!')",
                        "language": "python",
                        "created_at": "2025-11-30T10:00:00Z",
                        "updated_at": "2025-11-30T11:30:00Z"
                    }
                }
            }
        },
        400: {
            "description": "Invalid UUID format",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid room ID format: not-a-uuid"
                    }
                }
            }
        },
        404: {
            "description": "Room not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Room not found: 550e8400-e29b-41d4-a716-446655440000"
                    }
                }
            }
        }
    }
)
async def get_room(
    room_id: str,
    db: AsyncSession = Depends(get_db)
) -> RoomResponse:
    """
    Get a room by its ID.
    
    Retrieves the complete details of a room including its current code,
    programming language, and creation/update timestamps.
    
    Args:
        room_id: UUID of the room to retrieve
        db: Database session (injected)
    
    Returns:
        RoomResponse with all room details
        
    Raises:
        HTTPException 400: If room_id is not a valid UUID
        HTTPException 404: If room doesn't exist
        HTTPException 500: If database error occurs
        
    Example:
        ```
        GET /api/v1/rooms/550e8400-e29b-41d4-a716-446655440000
        
        Response (200):
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "code": "def hello():\n    print('Hello, World!')",
            "language": "python",
            "created_at": "2025-11-30T10:00:00Z",
            "updated_at": "2025-11-30T11:30:00Z"
        }
        ```
    """
    logger.debug(f"Fetching room: {room_id}")
    
    try:
        room = await RoomService.get_room(db, room_id)
        
        if not room:
            logger.warning(f"Room not found: {room_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Room not found: {room_id}"
            )
        
        logger.debug(f"Room found: {room_id}")
        return RoomResponse.model_validate(room)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching room {room_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching the room"
        )


@router.put(
    "/{room_id}/code",
    response_model=RoomResponse,
    status_code=status.HTTP_200_OK,
    summary="Update room code",
    description="Updates the code content of a room. The updated_at timestamp is automatically updated.",
    responses={
        200: {
            "description": "Code updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "code": "def fibonacci(n):\n    return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)",
                        "language": "python",
                        "created_at": "2025-11-30T10:00:00Z",
                        "updated_at": "2025-11-30T12:00:00Z"
                    }
                }
            }
        },
        400: {
            "description": "Invalid request",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_uuid": {
                            "value": {"detail": "Invalid room ID format: not-a-uuid"}
                        },
                        "code_too_long": {
                            "value": {"detail": "Code length (50001) exceeds maximum of 50,000 characters"}
                        }
                    }
                }
            }
        },
        404: {
            "description": "Room not found"
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["body", "code"],
                                "msg": "field required",
                                "type": "value_error.missing"
                            }
                        ]
                    }
                }
            }
        }
    }
)
async def update_room_code(
    room_id: str,
    update: CodeUpdate,
    db: AsyncSession = Depends(get_db)
) -> RoomResponse:
    """
    Update the code content of a room.
    
    Updates the room's code and automatically updates the updated_at timestamp.
    Optionally includes the user_id for tracking who made the change.
    
    Args:
        room_id: UUID of the room to update
        update: Code update data (code and optional user_id)
        db: Database session (injected)
    
    Returns:
        RoomResponse with updated room details
        
    Raises:
        HTTPException 400: If room_id is invalid or code is too long
        HTTPException 404: If room doesn't exist
        HTTPException 422: If request body is invalid
        HTTPException 500: If database error occurs
        
    Example:
        ```
        PUT /api/v1/rooms/550e8400-e29b-41d4-a716-446655440000/code
        {
            "code": "def hello():\n    print('Hello!')",
            "user_id": "user_123"
        }
        
        Response (200):
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "code": "def hello():\n    print('Hello!')",
            "language": "python",
            "created_at": "2025-11-30T10:00:00Z",
            "updated_at": "2025-11-30T12:00:00Z"
        }
        ```
    """
    logger.info(f"Updating code for room: {room_id}, user: {update.user_id or 'anonymous'}")
    
    try:
        updated_room = await RoomService.update_room_code(
            db,
            room_id,
            update.code
        )
        
        logger.info(f"Room code updated successfully: {room_id}")
        return RoomResponse.model_validate(updated_room)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating room {room_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the room"
        )


@router.delete(
    "/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a room",
    description="Permanently deletes a room from the database.",
    responses={
        204: {
            "description": "Room deleted successfully"
        },
        400: {
            "description": "Invalid UUID format",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid room ID format: not-a-uuid"
                    }
                }
            }
        },
        404: {
            "description": "Room not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Room not found: 550e8400-e29b-41d4-a716-446655440000"
                    }
                }
            }
        }
    }
)
async def delete_room(
    room_id: str,
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Delete a room.
    
    Permanently removes a room from the database. This operation cannot be undone.
    All room data including code and history will be lost.
    
    Args:
        room_id: UUID of the room to delete
        db: Database session (injected)
    
    Returns:
        None (204 No Content)
        
    Raises:
        HTTPException 400: If room_id is not a valid UUID
        HTTPException 404: If room doesn't exist
        HTTPException 500: If database error occurs
        
    Example:
        ```
        DELETE /api/v1/rooms/550e8400-e29b-41d4-a716-446655440000
        
        Response: 204 No Content
        ```
    """
    logger.info(f"Deleting room: {room_id}")
    
    try:
        # First check if room exists
        room = await RoomService.get_room(db, room_id)
        
        if not room:
            logger.warning(f"Room not found for deletion: {room_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Room not found: {room_id}"
            )
        
        # Delete the room
        await db.delete(room)
        await db.commit()
        
        logger.info(f"Room deleted successfully: {room_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error deleting room {room_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting the room"
        )

