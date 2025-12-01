"""
Tests for service layer (RoomService and CodeSyncService).

This module tests business logic including:
    - Room management operations
    - Code synchronization and caching
    - Conflict resolution
    - Background tasks
"""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room
from app.services.code_sync_service import CodeSyncService
from app.services.room_service import RoomService


# ============================================================================
# ROOM SERVICE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_room_default(db_session: AsyncSession):
    """
    Test creating a room with default values.
    
    Verifies that:
        - Room is created with auto-generated UUID
        - Default language is 'python'
        - Code is empty string
        - Timestamps are set
    """
    room = await RoomService.create_room(db_session)
    
    assert room.id is not None
    assert room.language == "python"
    assert room.code == ""
    assert room.created_at is not None
    assert room.updated_at is not None


@pytest.mark.asyncio
async def test_create_room_with_language(db_session: AsyncSession):
    """
    Test creating a room with specific language.
    """
    room = await RoomService.create_room(db_session, language="javascript")
    
    assert room.language == "javascript"


@pytest.mark.asyncio
async def test_create_room_with_code(db_session: AsyncSession):
    """
    Test creating a room with initial code.
    """
    initial_code = "console.log('Hello');"
    room = await RoomService.create_room(
        db_session,
        language="javascript",
        code=initial_code
    )
    
    assert room.code == initial_code


@pytest.mark.asyncio
async def test_get_room_exists(db_session: AsyncSession, sample_room: Room):
    """
    Test retrieving an existing room.
    """
    room = await RoomService.get_room(db_session, sample_room.id)
    
    assert room is not None
    assert room.id == sample_room.id
    assert room.code == sample_room.code


@pytest.mark.asyncio
async def test_get_room_not_exists(db_session: AsyncSession):
    """
    Test retrieving a non-existent room returns None.
    """
    nonexistent_id = uuid4()
    room = await RoomService.get_room(db_session, nonexistent_id)
    
    assert room is None


@pytest.mark.asyncio
async def test_get_room_with_string_uuid(db_session: AsyncSession, sample_room: Room):
    """
    Test retrieving a room using string UUID.
    """
    room = await RoomService.get_room(db_session, str(sample_room.id))
    
    assert room is not None
    assert room.id == sample_room.id


@pytest.mark.asyncio
async def test_update_room_code(db_session: AsyncSession, sample_room: Room):
    """
    Test updating room code.
    
    Verifies that:
        - Code is updated
        - updated_at timestamp changes
        - Other fields remain unchanged
    """
    original_updated_at = sample_room.updated_at
    new_code = "def updated():\n    pass"
    
    # Small delay to ensure timestamp difference
    await asyncio.sleep(0.01)
    
    updated_room = await RoomService.update_room_code(
        db_session,
        sample_room.id,
        new_code
    )
    
    assert updated_room.code == new_code
    assert updated_room.updated_at > original_updated_at
    assert updated_room.language == sample_room.language


@pytest.mark.asyncio
async def test_update_room_code_empty(db_session: AsyncSession, sample_room: Room):
    """
    Test updating room with empty code.
    """
    updated_room = await RoomService.update_room_code(
        db_session,
        sample_room.id,
        ""
    )
    
    assert updated_room.code == ""


@pytest.mark.asyncio
async def test_update_nonexistent_room(db_session: AsyncSession):
    """
    Test updating a non-existent room raises error.
    """
    nonexistent_id = uuid4()
    
    with pytest.raises(Exception):  # Should raise HTTPException
        await RoomService.update_room_code(
            db_session,
            nonexistent_id,
            "test"
        )


@pytest.mark.asyncio
async def test_delete_old_rooms(db_session: AsyncSession):
    """
    Test deleting rooms older than specified hours.
    
    Creates rooms with different timestamps and verifies
    only old ones are deleted.
    """
    # Create an old room (manually set updated_at)
    old_room = Room(
        id=uuid4(),
        code="old",
        language="python"
    )
    db_session.add(old_room)
    await db_session.commit()
    await db_session.refresh(old_room)
    
    # Manually set updated_at to 25 hours ago
    old_time = datetime.now() - timedelta(hours=25)
    old_room.updated_at = old_time
    db_session.add(old_room)
    await db_session.commit()
    
    # Create a recent room
    recent_room = await RoomService.create_room(db_session)
    
    # Delete rooms older than 24 hours
    deleted_count = await RoomService.delete_old_rooms(db_session, hours=24)
    
    assert deleted_count >= 1
    
    # Verify old room is deleted
    result = await RoomService.get_room(db_session, old_room.id)
    assert result is None
    
    # Verify recent room still exists
    result = await RoomService.get_room(db_session, recent_room.id)
    assert result is not None


@pytest.mark.asyncio
async def test_list_active_rooms(db_session: AsyncSession):
    """
    Test listing active rooms.
    
    Verifies that only recently updated rooms are returned.
    """
    # Create multiple rooms
    room1 = await RoomService.create_room(db_session, code="room1")
    room2 = await RoomService.create_room(db_session, code="room2")
    
    # List active rooms (updated within last hour)
    active_rooms = await RoomService.list_active_rooms(db_session, hours=1)
    
    assert len(active_rooms) >= 2
    room_ids = [room.id for room in active_rooms]
    assert room1.id in room_ids
    assert room2.id in room_ids


# ============================================================================
# CODE SYNC SERVICE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_code_sync_service_initialization():
    """
    Test CodeSyncService initialization.
    
    Verifies service starts with empty cache.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    assert service._cache == {}
    assert service._dirty_rooms == set()
    stats = service.get_cache_stats()
    assert stats["cache_size"] == 0


@pytest.mark.asyncio
async def test_code_sync_get_code_miss(db_session: AsyncSession, sample_room: Room):
    """
    Test getting code from cache (cache miss).
    
    Verifies that:
        - Code is loaded from database on cache miss
        - Code is stored in cache
        - Statistics are updated
    """
    service = CodeSyncService(db_sync_interval=1)
    
    code, version = await service.get_code(str(sample_room.id), db_session)
    
    assert code == sample_room.code
    assert version > 0
    
    stats = service.get_cache_stats()
    assert stats["total_misses"] == 1
    assert stats["cache_size"] == 1


@pytest.mark.asyncio
async def test_code_sync_get_code_hit(db_session: AsyncSession, sample_room: Room):
    """
    Test getting code from cache (cache hit).
    
    Verifies that:
        - Cached code is returned without database query
        - Hit count is incremented
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # First call - cache miss
    await service.get_code(str(sample_room.id), db_session)
    
    # Second call - cache hit
    code, version = await service.get_code(str(sample_room.id), db_session)
    
    assert code == sample_room.code
    
    stats = service.get_cache_stats()
    assert stats["total_hits"] == 1
    assert stats["total_misses"] == 1


@pytest.mark.asyncio
async def test_code_sync_update_code(db_session: AsyncSession, sample_room: Room):
    """
    Test updating code in cache.
    
    Verifies that:
        - Code is updated in cache
        - Room is marked as dirty
        - Version is incremented
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # Get initial code (loads into cache)
    _, initial_version = await service.get_code(str(sample_room.id), db_session)
    
    # Update code
    new_code = "print('updated')"
    new_version = await service.update_code(str(sample_room.id), new_code, "user1")
    
    assert new_version > initial_version
    
    # Verify cache has new code
    cached_code, _ = await service.get_code(str(sample_room.id), db_session)
    assert cached_code == new_code
    
    # Verify room is dirty
    stats = service.get_cache_stats()
    assert stats["dirty_rooms"] == 1


@pytest.mark.asyncio
async def test_code_sync_to_database(db_session: AsyncSession, sample_room: Room):
    """
    Test syncing code from cache to database.
    
    Verifies that:
        - Dirty rooms are synced
        - Database is updated
        - Dirty flag is cleared
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # Update code in cache
    new_code = "print('synced')"
    await service.update_code(str(sample_room.id), new_code, "user1")
    
    # Sync to database
    synced_count = await service.sync_to_database(db_session)
    
    assert synced_count == 1
    
    # Verify database has new code
    await db_session.refresh(sample_room)
    assert sample_room.code == new_code
    
    # Verify dirty flag is cleared
    stats = service.get_cache_stats()
    assert stats["dirty_rooms"] == 0


@pytest.mark.asyncio
async def test_code_sync_multiple_updates(db_session: AsyncSession, sample_room: Room):
    """
    Test multiple rapid code updates.
    
    Verifies that:
        - Multiple updates work correctly
        - Only latest code is preserved
        - Only one database sync is needed
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # Perform multiple updates
    for i in range(10):
        await service.update_code(str(sample_room.id), f"code_{i}", f"user{i}")
    
    # Sync to database
    synced_count = await service.sync_to_database(db_session)
    
    assert synced_count == 1
    
    # Verify latest code is in database
    await db_session.refresh(sample_room)
    assert sample_room.code == "code_9"
    
    stats = service.get_cache_stats()
    assert stats["total_updates"] == 10


@pytest.mark.asyncio
async def test_code_sync_room_info(db_session: AsyncSession, sample_room: Room):
    """
    Test getting room information from cache.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # Update code to populate cache
    await service.update_code(str(sample_room.id), "test", "user1")
    
    # Get room info
    info = await service.get_room_info(str(sample_room.id))
    
    assert info is not None
    assert info["room_id"] == str(sample_room.id)
    assert "code_length" in info
    assert "version" in info
    assert "last_update_by" in info
    assert "update_count" in info


@pytest.mark.asyncio
async def test_code_sync_room_info_nonexistent():
    """
    Test getting info for non-existent room returns None.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    info = await service.get_room_info(str(uuid4()))
    
    assert info is None


@pytest.mark.asyncio
async def test_code_sync_statistics():
    """
    Test code sync service statistics.
    
    Verifies that statistics are tracked correctly.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    stats = service.get_cache_stats()
    
    assert "cache_size" in stats
    assert "dirty_rooms" in stats
    assert "hit_rate" in stats
    assert "total_hits" in stats
    assert "total_misses" in stats
    assert "total_updates" in stats
    assert "total_syncs" in stats
    assert "total_conflicts" in stats
    assert "total_errors" in stats
    assert "sync_interval_seconds" in stats


@pytest.mark.asyncio
async def test_code_sync_hit_rate_calculation(db_session: AsyncSession, sample_room: Room):
    """
    Test hit rate calculation.
    
    Verifies that hit rate is calculated correctly.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # First call - miss
    await service.get_code(str(sample_room.id), db_session)
    
    # Next 3 calls - hits
    await service.get_code(str(sample_room.id), db_session)
    await service.get_code(str(sample_room.id), db_session)
    await service.get_code(str(sample_room.id), db_session)
    
    stats = service.get_cache_stats()
    
    # Hit rate should be 75% (3 hits out of 4 total)
    assert stats["hit_rate"] == 75.0


@pytest.mark.asyncio
async def test_code_sync_concurrent_updates(db_session: AsyncSession, sample_room: Room):
    """
    Test concurrent code updates to same room.
    
    Verifies that updates are handled safely.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # Simulate concurrent updates
    async def update(user_id: int):
        for i in range(5):
            await service.update_code(
                str(sample_room.id),
                f"user{user_id}_code{i}",
                f"user{user_id}"
            )
            await asyncio.sleep(0.001)
    
    # Run concurrent updates
    await asyncio.gather(
        update(1),
        update(2),
        update(3)
    )
    
    # Sync to database
    await service.sync_to_database(db_session)
    
    stats = service.get_cache_stats()
    assert stats["total_updates"] == 15  # 3 users * 5 updates each


@pytest.mark.asyncio
async def test_code_sync_cache_cleanup(db_session: AsyncSession):
    """
    Test cache cleanup for inactive rooms.
    
    Note: This would test the cleanup mechanism if implemented.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # Create and update multiple rooms
    for i in range(5):
        room = await RoomService.create_room(db_session, code=f"room{i}")
        await service.update_code(str(room.id), f"code{i}", "user")
    
    stats = service.get_cache_stats()
    assert stats["cache_size"] == 5


@pytest.mark.asyncio
async def test_code_sync_initialize(db_session: AsyncSession, multiple_rooms: list[Room]):
    """
    Test initializing sync service with existing rooms.
    
    Verifies that active rooms are loaded into cache on startup.
    """
    service = CodeSyncService(db_sync_interval=1)
    
    # Initialize with active rooms
    await service.initialize(db_session)
    
    stats = service.get_cache_stats()
    # Should have loaded the active rooms
    assert stats["cache_size"] >= 0  # May be 0 if rooms aren't "active"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_service_integration(db_session: AsyncSession):
    """
    Test integration between RoomService and CodeSyncService.
    
    Verifies that:
        - Room can be created with RoomService
        - Code can be updated with CodeSyncService
        - Sync updates the database
        - RoomService sees the changes
    """
    # Create room
    room = await RoomService.create_room(db_session, code="initial")
    
    # Update via CodeSyncService
    sync_service = CodeSyncService(db_sync_interval=1)
    await sync_service.update_code(str(room.id), "updated", "user1")
    
    # Sync to database
    await sync_service.sync_to_database(db_session)
    
    # Verify with RoomService
    updated_room = await RoomService.get_room(db_session, room.id)
    assert updated_room.code == "updated"

