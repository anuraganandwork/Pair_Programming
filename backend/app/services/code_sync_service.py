"""
Code synchronization service for real-time collaboration.

This service provides an in-memory cache layer between WebSocket connections
and the database, enabling fast code updates with periodic database syncing.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.room_service import RoomService

# Configure logging
logger = logging.getLogger(__name__)


class CodeSyncService:
    """
    Service for managing code synchronization with caching and background syncing.
    
    Maintains an in-memory cache of active rooms for fast read/write operations,
    with periodic background syncing to the database. Uses locks for thread-safety
    and implements cleanup for inactive rooms.
    
    Architecture:
        WebSocket → CodeSyncService (cache) → Background Task → Database
        
    Benefits:
        - Fast updates (no DB wait)
        - Reduced database load
        - Automatic cleanup
        - Monitoring and stats
    
    Attributes:
        _cache: In-memory cache of room data
        _dirty_rooms: Set of room IDs with unsaved changes
        _cache_lock: Lock for thread-safe cache operations
        _db_sync_interval: Seconds between database syncs (default: 2)
        _cache_stats: Statistics for monitoring
        _background_task: Reference to background sync task
    """
    
    def __init__(self, db_sync_interval: int = 2):
        """
        Initialize the code sync service.
        
        Args:
            db_sync_interval: Seconds between database syncs (default: 2)
        """
        # Cache structure: {room_id: {code, last_updated, lock, last_access}}
        self._cache: Dict[str, Dict] = {}
        
        # Track rooms with unsaved changes
        self._dirty_rooms: Set[str] = set()
        
        # Global lock for cache modifications
        self._cache_lock = asyncio.Lock()
        
        # Sync interval
        self._db_sync_interval = db_sync_interval
        
        # Statistics for monitoring
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "updates": 0,
            "syncs": 0,
            "conflicts": 0,
            "errors": 0,
        }
        
        # Background task reference
        self._background_task: Optional[asyncio.Task] = None
        
        logger.info(
            f"CodeSyncService initialized with sync interval: {db_sync_interval}s"
        )
    
    async def initialize(self, db: AsyncSession):
        """
        Initialize the service by loading active rooms from database.
        
        Should be called during application startup to warm the cache
        with recently active rooms.
        
        Args:
            db: Database session
        """
        logger.info("Initializing CodeSyncService - loading active rooms into cache")
        
        try:
            # Load rooms active in the last hour
            active_rooms = await RoomService.list_active_rooms(db, hours=1)
            
            async with self._cache_lock:
                for room in active_rooms:
                    self._cache[str(room.id)] = {
                        "code": room.code or "",
                        "last_updated": room.updated_at,
                        "last_access": datetime.utcnow(),
                        "lock": asyncio.Lock(),
                    }
            
            logger.info(f"Loaded {len(active_rooms)} active rooms into cache")
            
        except Exception as e:
            logger.error(f"Error initializing cache: {e}", exc_info=True)
            # Don't fail startup - just start with empty cache
    
    async def get_code(self, room_id: str, db: AsyncSession) -> str:
        """
        Get code for a room from cache or database.
        
        Checks cache first for fast access. If not in cache, loads from
        database and caches for future access.
        
        Args:
            room_id: Room identifier
            db: Database session
            
        Returns:
            str: Current code in the room
            
        Raises:
            Exception: If room not found or database error
        """
        # Check cache first
        async with self._cache_lock:
            if room_id in self._cache:
                self._cache_stats["hits"] += 1
                self._cache[room_id]["last_access"] = datetime.utcnow()
                code = self._cache[room_id]["code"]
                logger.debug(f"Cache hit for room {room_id}")
                return code
        
        # Cache miss - load from database
        self._cache_stats["misses"] += 1
        logger.debug(f"Cache miss for room {room_id}, loading from database")
        
        try:
            room = await RoomService.get_room(db, room_id)
            
            if not room:
                logger.warning(f"Room {room_id} not found in database")
                raise ValueError(f"Room not found: {room_id}")
            
            code = room.code or ""
            
            # Add to cache
            async with self._cache_lock:
                self._cache[room_id] = {
                    "code": code,
                    "last_updated": room.updated_at,
                    "last_access": datetime.utcnow(),
                    "lock": asyncio.Lock(),
                }
            
            logger.debug(f"Loaded room {room_id} into cache")
            return code
            
        except Exception as e:
            logger.error(f"Error loading room {room_id} from database: {e}")
            self._cache_stats["errors"] += 1
            raise
    
    async def update_code(
        self,
        room_id: str,
        code: str,
        user_id: Optional[str] = None
    ) -> None:
        """
        Update code in cache immediately.
        
        Updates the in-memory cache for fast access and marks the room as dirty
        for background database sync. Uses per-room locks to prevent race conditions.
        
        Args:
            room_id: Room identifier
            code: New code content
            user_id: Optional user who made the change
        """
        logger.debug(
            f"Updating code for room {room_id} "
            f"(user: {user_id or 'unknown'}, length: {len(code)})"
        )
        
        try:
            # Ensure room is in cache
            async with self._cache_lock:
                if room_id not in self._cache:
                    # Initialize cache entry if not exists
                    self._cache[room_id] = {
                        "code": code,
                        "last_updated": datetime.utcnow(),
                        "last_access": datetime.utcnow(),
                        "lock": asyncio.Lock(),
                    }
                else:
                    # Get the room's lock
                    room_lock = self._cache[room_id]["lock"]
            
            # Use room-specific lock for update
            if room_id in self._cache:
                async with self._cache[room_id]["lock"]:
                    # Check for conflict (simple last-write-wins)
                    if self._cache[room_id]["code"] != code:
                        # Update cache
                        self._cache[room_id]["code"] = code
                        self._cache[room_id]["last_updated"] = datetime.utcnow()
                        self._cache[room_id]["last_access"] = datetime.utcnow()
                        
                        # Mark as dirty for DB sync
                        async with self._cache_lock:
                            self._dirty_rooms.add(room_id)
                        
                        self._cache_stats["updates"] += 1
                        logger.debug(f"Code updated in cache for room {room_id}")
            
        except Exception as e:
            logger.error(f"Error updating code for room {room_id}: {e}", exc_info=True)
            self._cache_stats["errors"] += 1
    
    async def sync_to_database(self, db: AsyncSession) -> int:
        """
        Sync dirty rooms from cache to database.
        
        Performs batch updates of all rooms with unsaved changes. Uses
        efficient bulk operations and handles errors gracefully.
        
        Args:
            db: Database session
            
        Returns:
            int: Number of rooms successfully synced
        """
        # Get snapshot of dirty rooms
        async with self._cache_lock:
            rooms_to_sync = list(self._dirty_rooms)
        
        if not rooms_to_sync:
            return 0
        
        logger.info(f"Syncing {len(rooms_to_sync)} dirty rooms to database")
        
        synced_count = 0
        errors = []
        
        for room_id in rooms_to_sync:
            try:
                # Get code from cache
                async with self._cache_lock:
                    if room_id not in self._cache:
                        continue
                    
                    code = self._cache[room_id]["code"]
                
                # Update database
                await RoomService.update_room_code(db, room_id, code)
                
                # Remove from dirty set
                async with self._cache_lock:
                    self._dirty_rooms.discard(room_id)
                
                synced_count += 1
                logger.debug(f"Synced room {room_id} to database")
                
            except Exception as e:
                error_msg = f"Error syncing room {room_id}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                self._cache_stats["errors"] += 1
                # Continue with other rooms
        
        self._cache_stats["syncs"] += 1
        
        if errors:
            logger.warning(
                f"Completed sync with {len(errors)} errors out of {len(rooms_to_sync)} rooms"
            )
        else:
            logger.info(f"Successfully synced {synced_count} rooms to database")
        
        return synced_count
    
    async def start_background_sync(self, db_session_factory):
        """
        Start background task for periodic database syncing.
        
        Runs continuously until cancelled, syncing dirty rooms to the database
        at regular intervals. Should be started during application startup.
        
        Args:
            db_session_factory: Factory function to create database sessions
        """
        logger.info(
            f"Starting background sync task (interval: {self._db_sync_interval}s)"
        )
        
        async def sync_loop():
            """Background sync loop."""
            while True:
                try:
                    await asyncio.sleep(self._db_sync_interval)
                    
                    # Create new database session for sync
                    async with db_session_factory() as db:
                        synced = await self.sync_to_database(db)
                        
                        if synced > 0:
                            logger.debug(f"Background sync: {synced} rooms")
                
                except asyncio.CancelledError:
                    logger.info("Background sync task cancelled")
                    break
                
                except Exception as e:
                    logger.error(f"Error in background sync: {e}", exc_info=True)
                    # Continue running despite errors
        
        self._background_task = asyncio.create_task(sync_loop())
        return self._background_task
    
    async def stop_background_sync(self):
        """Stop the background sync task."""
        if self._background_task:
            logger.info("Stopping background sync task")
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
    
    async def handle_conflict(
        self,
        room_id: str,
        local_code: str,
        remote_code: str
    ) -> str:
        """
        Handle code conflict resolution.
        
        For MVP, uses simple last-write-wins strategy. In production,
        consider using Operational Transform (OT) or Conflict-free
        Replicated Data Types (CRDT) for proper conflict resolution.
        
        Args:
            room_id: Room identifier
            local_code: Code in cache
            remote_code: Code from update
            
        Returns:
            str: Resolved code (currently just returns remote_code)
        """
        logger.warning(
            f"Code conflict detected for room {room_id}. "
            f"Using last-write-wins strategy."
        )
        
        self._cache_stats["conflicts"] += 1
        
        # For now, just use the most recent (last-write-wins)
        # In production, implement proper OT or CRDT
        return remote_code
    
    async def cleanup_inactive_rooms(self, max_age_hours: int = 1) -> int:
        """
        Remove inactive rooms from cache to free memory.
        
        Removes rooms that haven't been accessed within the specified
        time period. Dirty rooms are synced before removal.
        
        Args:
            max_age_hours: Hours of inactivity before removal (default: 1)
            
        Returns:
            int: Number of rooms removed from cache
        """
        logger.info(f"Cleaning up rooms inactive for {max_age_hours} hour(s)")
        
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        rooms_to_remove = []
        
        # Find inactive rooms
        async with self._cache_lock:
            for room_id, room_data in self._cache.items():
                last_access = room_data.get("last_access", datetime.utcnow())
                if last_access < cutoff_time:
                    rooms_to_remove.append(room_id)
        
        if not rooms_to_remove:
            logger.debug("No inactive rooms to cleanup")
            return 0
        
        # Sync dirty rooms before removal
        rooms_to_sync = [r for r in rooms_to_remove if r in self._dirty_rooms]
        if rooms_to_sync:
            logger.info(f"Syncing {len(rooms_to_sync)} dirty rooms before cleanup")
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                await self.sync_to_database(db)
        
        # Remove from cache
        async with self._cache_lock:
            for room_id in rooms_to_remove:
                if room_id in self._cache:
                    del self._cache[room_id]
                self._dirty_rooms.discard(room_id)
        
        logger.info(f"Removed {len(rooms_to_remove)} inactive rooms from cache")
        return len(rooms_to_remove)
    
    def get_cache_stats(self) -> dict:
        """
        Get cache statistics for monitoring.
        
        Returns:
            dict: Statistics including cache size, hit rate, and operation counts
        """
        total_requests = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (
            self._cache_stats["hits"] / total_requests * 100
            if total_requests > 0
            else 0
        )
        
        return {
            "cache_size": len(self._cache),
            "dirty_rooms": len(self._dirty_rooms),
            "hit_rate": round(hit_rate, 2),
            "total_hits": self._cache_stats["hits"],
            "total_misses": self._cache_stats["misses"],
            "total_updates": self._cache_stats["updates"],
            "total_syncs": self._cache_stats["syncs"],
            "total_conflicts": self._cache_stats["conflicts"],
            "total_errors": self._cache_stats["errors"],
            "sync_interval_seconds": self._db_sync_interval,
        }
    
    async def force_sync_room(self, room_id: str, db: AsyncSession) -> bool:
        """
        Force immediate database sync for a specific room.
        
        Useful for important operations that need immediate persistence.
        
        Args:
            room_id: Room to sync
            db: Database session
            
        Returns:
            bool: True if sync successful, False otherwise
        """
        logger.info(f"Force syncing room {room_id} to database")
        
        try:
            async with self._cache_lock:
                if room_id not in self._cache:
                    logger.warning(f"Room {room_id} not in cache")
                    return False
                
                code = self._cache[room_id]["code"]
            
            await RoomService.update_room_code(db, room_id, code)
            
            async with self._cache_lock:
                self._dirty_rooms.discard(room_id)
            
            logger.info(f"Successfully force-synced room {room_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error force-syncing room {room_id}: {e}", exc_info=True)
            self._cache_stats["errors"] += 1
            return False
    
    async def invalidate_cache(self, room_id: str) -> None:
        """
        Remove a room from cache.
        
        Forces next access to reload from database. Useful when external
        updates occur outside the cache.
        
        Args:
            room_id: Room to invalidate
        """
        logger.debug(f"Invalidating cache for room {room_id}")
        
        async with self._cache_lock:
            if room_id in self._cache:
                del self._cache[room_id]
            self._dirty_rooms.discard(room_id)
    
    async def get_room_info(self, room_id: str) -> Optional[dict]:
        """
        Get information about a cached room.
        
        Args:
            room_id: Room identifier
            
        Returns:
            dict: Room info or None if not in cache
        """
        async with self._cache_lock:
            if room_id not in self._cache:
                return None
            
            room_data = self._cache[room_id]
            return {
                "room_id": room_id,
                "code_length": len(room_data["code"]),
                "last_updated": room_data["last_updated"].isoformat(),
                "last_access": room_data["last_access"].isoformat(),
                "is_dirty": room_id in self._dirty_rooms,
            }


# Global singleton instance
_code_sync_service: Optional[CodeSyncService] = None


def get_code_sync_service() -> CodeSyncService:
    """
    Get the global CodeSyncService instance.
    
    Returns:
        CodeSyncService: Singleton service instance
    """
    global _code_sync_service
    
    if _code_sync_service is None:
        _code_sync_service = CodeSyncService()
    
    return _code_sync_service

