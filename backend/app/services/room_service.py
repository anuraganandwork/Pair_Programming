"""
Room management service for business logic operations.

This module provides the RoomService class with all CRUD operations
for managing coding rooms, including creation, retrieval, updates,
and cleanup of old rooms.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room

# Configure logging
logger = logging.getLogger(__name__)


class RoomService:
    """
    Service class for room management operations.
    
    This class follows the dependency injection pattern - all methods
    accept an AsyncSession parameter rather than creating sessions internally.
    This makes the service more testable and follows SOLID principles.
    
    All methods include comprehensive error handling and logging.
    """
    
    @staticmethod
    async def create_room(
        db: AsyncSession,
        language: str = "python",
        initial_code: Optional[str] = None
    ) -> Room:
        """
        Create a new coding room.
        
        Generates a new UUID for the room and creates it with default or
        specified values. The room is immediately committed to the database.
        
        Args:
            db: Database session for the operation
            language: Programming language for the room (default: "python")
            initial_code: Optional initial code content
            
        Returns:
            Room: The newly created room object with all fields populated
            
        Raises:
            HTTPException: 500 if database operation fails
            
        Example:
            ```python
            room = await RoomService.create_room(
                db,
                language="javascript",
                initial_code="console.log('Hello');"
            )
            print(f"Created room: {room.id}")
            ```
        """
        try:
            # Generate new UUID for the room
            room_id = uuid.uuid4()
            
            logger.info(
                f"Creating new room with ID: {room_id}, language: {language}"
            )
            
            # Create room instance
            new_room = Room(
                id=room_id,
                code=initial_code,
                language=language.lower(),
            )
            
            # Add to session and commit
            db.add(new_room)
            await db.commit()
            await db.refresh(new_room)
            
            logger.info(f"Successfully created room: {room_id}")
            return new_room
            
        except IntegrityError as e:
            await db.rollback()
            logger.error(f"Integrity error creating room: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create room due to database constraint violation"
            )
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Database error creating room: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create room due to database error"
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Unexpected error creating room: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while creating room"
            )
    
    @staticmethod
    async def get_room(
        db: AsyncSession,
        room_id: str | uuid.UUID
    ) -> Optional[Room]:
        """
        Retrieve a room by its ID.
        
        Queries the database for a room with the specified UUID.
        Returns None if the room doesn't exist.
        
        Args:
            db: Database session for the operation
            room_id: UUID of the room (can be string or UUID object)
            
        Returns:
            Optional[Room]: Room object if found, None otherwise
            
        Raises:
            HTTPException: 400 if room_id is invalid UUID format
            HTTPException: 500 if database operation fails
            
        Example:
            ```python
            room = await RoomService.get_room(db, "550e8400-e29b-41d4-a716-446655440000")
            if room:
                print(f"Room code: {room.code}")
            else:
                print("Room not found")
            ```
        """
        try:
            # Convert string to UUID if needed
            if isinstance(room_id, str):
                try:
                    room_uuid = uuid.UUID(room_id)
                except ValueError:
                    logger.warning(f"Invalid UUID format: {room_id}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid room ID format: {room_id}"
                    )
            else:
                room_uuid = room_id
            
            logger.debug(f"Fetching room: {room_uuid}")
            
            # Query room by ID
            result = await db.execute(
                select(Room).where(Room.id == room_uuid)
            )
            room = result.scalar_one_or_none()
            
            if room:
                logger.debug(f"Found room: {room_uuid}")
            else:
                logger.debug(f"Room not found: {room_uuid}")
            
            return room
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching room {room_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch room due to database error"
            )
        except Exception as e:
            logger.error(f"Unexpected error fetching room {room_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while fetching room"
            )
    
    @staticmethod
    async def update_room_code(
        db: AsyncSession,
        room_id: str | uuid.UUID,
        code: str
    ) -> Room:
        """
        Update the code content of a room.
        
        Updates the room's code field and automatically updates the updated_at
        timestamp. Commits the changes to the database.
        
        Args:
            db: Database session for the operation
            room_id: UUID of the room to update
            code: New code content (max 50,000 characters)
            
        Returns:
            Room: The updated room object
            
        Raises:
            HTTPException: 404 if room not found
            HTTPException: 400 if code is too long or room_id is invalid
            HTTPException: 500 if database operation fails
            
        Example:
            ```python
            updated_room = await RoomService.update_room_code(
                db,
                room_id="550e8400-e29b-41d4-a716-446655440000",
                code="def hello(): print('Hello!')"
            )
            print(f"Updated at: {updated_room.updated_at}")
            ```
        """
        try:
            # Validate code length
            if len(code) > 50000:
                logger.warning(f"Code too long: {len(code)} characters")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Code length ({len(code)}) exceeds maximum of 50,000 characters"
                )
            
            logger.info(f"Updating code for room: {room_id}")
            
            # Fetch the room
            room = await RoomService.get_room(db, room_id)
            
            if not room:
                logger.warning(f"Room not found for update: {room_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Room not found: {room_id}"
                )
            
            # Update code and timestamp
            room.code = code
            room.updated_at = datetime.utcnow()
            
            # Commit changes
            await db.commit()
            await db.refresh(room)
            
            logger.info(f"Successfully updated room: {room_id}")
            return room
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Database error updating room {room_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update room due to database error"
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Unexpected error updating room {room_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while updating room"
            )
    
    @staticmethod
    async def delete_old_rooms(
        db: AsyncSession,
        hours: int = 24
    ) -> int:
        """
        Delete rooms that haven't been updated in the specified time period.
        
        This is a cleanup operation typically run by a background task.
        Deletes rooms where updated_at is older than the specified hours.
        
        Args:
            db: Database session for the operation
            hours: Number of hours of inactivity before deletion (default: 24)
            
        Returns:
            int: Number of rooms deleted
            
        Raises:
            HTTPException: 400 if hours is negative
            HTTPException: 500 if database operation fails
            
        Example:
            ```python
            # Delete rooms older than 48 hours
            count = await RoomService.delete_old_rooms(db, hours=48)
            print(f"Deleted {count} old rooms")
            ```
        """
        try:
            if hours < 0:
                logger.warning(f"Invalid hours value: {hours}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Hours must be a positive number"
                )
            
            # Calculate cutoff time
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            logger.info(f"Deleting rooms older than {hours} hours (before {cutoff_time})")
            
            # Delete old rooms
            result = await db.execute(
                delete(Room).where(Room.updated_at < cutoff_time)
            )
            
            deleted_count = result.rowcount or 0
            
            await db.commit()
            
            logger.info(f"Deleted {deleted_count} rooms older than {hours} hours")
            return deleted_count
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Database error deleting old rooms: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete old rooms due to database error"
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Unexpected error deleting old rooms: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while deleting old rooms"
            )
    
    @staticmethod
    async def list_active_rooms(
        db: AsyncSession,
        hours: int = 1
    ) -> list[Room]:
        """
        List rooms that have been active recently.
        
        Returns all rooms that have been updated within the specified
        number of hours. Useful for monitoring and admin dashboards.
        
        Args:
            db: Database session for the operation
            hours: Number of hours to consider as "active" (default: 1)
            
        Returns:
            list[Room]: List of active rooms, ordered by most recently updated
            
        Raises:
            HTTPException: 400 if hours is negative
            HTTPException: 500 if database operation fails
            
        Example:
            ```python
            # Get rooms active in last 2 hours
            active_rooms = await RoomService.list_active_rooms(db, hours=2)
            for room in active_rooms:
                print(f"Room {room.id}: {room.language}")
            ```
        """
        try:
            if hours < 0:
                logger.warning(f"Invalid hours value: {hours}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Hours must be a positive number"
                )
            
            # Calculate cutoff time
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            logger.debug(f"Fetching rooms active since {cutoff_time}")
            
            # Query active rooms
            result = await db.execute(
                select(Room)
                .where(Room.updated_at >= cutoff_time)
                .order_by(Room.updated_at.desc())
            )
            
            rooms = result.scalars().all()
            
            logger.info(f"Found {len(rooms)} active rooms in last {hours} hour(s)")
            return list(rooms)
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error listing active rooms: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to list active rooms due to database error"
            )
        except Exception as e:
            logger.error(f"Unexpected error listing active rooms: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while listing active rooms"
            )

