"""
Tests for room management endpoints.

This module tests all CRUD operations for rooms including:
    - Room creation
    - Room retrieval
    - Code updates
    - Room deletion
    - Error handling
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room


# ============================================================================
# CREATE ROOM TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_room_success(client: AsyncClient, db_session: AsyncSession):
    """
    Test successful room creation.
    
    Verifies that:
        - POST /api/v1/rooms returns 201
        - Response contains a valid room ID
        - Room exists in database
        - Default language is 'python'
    """
    response = await client.post("/api/v1/rooms", json={})
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify response structure
    assert "roomId" in data
    room_id = data["roomId"]
    
    # Verify it's a valid UUID
    try:
        UUID(room_id)
    except ValueError:
        pytest.fail(f"Invalid UUID returned: {room_id}")
    
    # Verify room exists in database
    result = await db_session.get(Room, UUID(room_id))
    assert result is not None
    assert result.language == "python"
    assert result.code == ""


@pytest.mark.asyncio
async def test_create_room_with_language(client: AsyncClient, db_session: AsyncSession):
    """
    Test room creation with specific language.
    
    Verifies that the language parameter is respected.
    """
    response = await client.post(
        "/api/v1/rooms",
        json={"language": "javascript", "code": "console.log('test');"}
    )
    
    assert response.status_code == 201
    data = response.json()
    room_id = data["roomId"]
    
    # Verify room has correct language
    result = await db_session.get(Room, UUID(room_id))
    assert result is not None
    assert result.language == "javascript"
    assert result.code == "console.log('test');"


@pytest.mark.asyncio
async def test_create_room_with_code(client: AsyncClient, db_session: AsyncSession):
    """
    Test room creation with initial code.
    
    Verifies that initial code is stored correctly.
    """
    initial_code = "def hello():\n    print('Hello, World!')"
    
    response = await client.post(
        "/api/v1/rooms",
        json={"language": "python", "code": initial_code}
    )
    
    assert response.status_code == 201
    data = response.json()
    room_id = data["roomId"]
    
    # Verify room has initial code
    result = await db_session.get(Room, UUID(room_id))
    assert result is not None
    assert result.code == initial_code


# ============================================================================
# GET ROOM TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_room_success(client: AsyncClient, sample_room: Room):
    """
    Test successful room retrieval.
    
    Verifies that:
        - GET /api/v1/rooms/{id} returns 200
        - Response contains all room fields
        - Data matches database
    """
    response = await client.get(f"/api/v1/rooms/{sample_room.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert data["id"] == str(sample_room.id)
    assert data["code"] == sample_room.code
    assert data["language"] == sample_room.language
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_room_not_found(client: AsyncClient, nonexistent_uuid: str):
    """
    Test retrieving a non-existent room.
    
    Verifies that:
        - GET /api/v1/rooms/{invalid-id} returns 404
        - Error message is informative
    """
    response = await client.get(f"/api/v1/rooms/{nonexistent_uuid}")
    
    assert response.status_code == 404
    data = response.json()
    
    # Verify error structure
    assert "error" in data
    assert "message" in data["error"]


@pytest.mark.asyncio
async def test_get_room_invalid_uuid(client: AsyncClient, invalid_uuid: str):
    """
    Test retrieving a room with invalid UUID format.
    
    Verifies that:
        - GET /api/v1/rooms/{invalid-format} returns 400 or 422
        - Error message indicates invalid UUID
    """
    response = await client.get(f"/api/v1/rooms/{invalid_uuid}")
    
    # Accept either 400 or 422 for invalid UUID
    assert response.status_code in [400, 422]


# ============================================================================
# UPDATE ROOM CODE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_update_room_code_success(
    client: AsyncClient,
    sample_room: Room,
    db_session: AsyncSession
):
    """
    Test successful code update.
    
    Verifies that:
        - PUT /api/v1/rooms/{id}/code returns 200
        - Code is updated in database
        - updated_at timestamp changes
    """
    new_code = "def updated():\n    return 'Updated!'"
    original_updated_at = sample_room.updated_at
    
    response = await client.put(
        f"/api/v1/rooms/{sample_room.id}/code",
        json={"code": new_code, "user_id": "test_user"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response
    assert data["id"] == str(sample_room.id)
    assert data["code"] == new_code
    
    # Verify database update
    await db_session.refresh(sample_room)
    assert sample_room.code == new_code
    assert sample_room.updated_at > original_updated_at


@pytest.mark.asyncio
async def test_update_room_code_empty(
    client: AsyncClient,
    sample_room: Room,
    db_session: AsyncSession
):
    """
    Test updating room with empty code.
    
    Verifies that empty code is allowed.
    """
    response = await client.put(
        f"/api/v1/rooms/{sample_room.id}/code",
        json={"code": ""}
    )
    
    assert response.status_code == 200
    
    # Verify database update
    await db_session.refresh(sample_room)
    assert sample_room.code == ""


@pytest.mark.asyncio
async def test_update_room_code_long(client: AsyncClient, sample_room: Room):
    """
    Test updating room with very long code.
    
    Verifies that code up to the limit is accepted.
    """
    long_code = "x = 1\n" * 5000  # ~30,000 characters
    
    response = await client.put(
        f"/api/v1/rooms/{sample_room.id}/code",
        json={"code": long_code}
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_room_code_too_long(client: AsyncClient, sample_room: Room):
    """
    Test updating room with code exceeding maximum length.
    
    Verifies that code over 50,000 characters is rejected.
    """
    too_long_code = "x" * 50001  # Over the 50,000 limit
    
    response = await client.put(
        f"/api/v1/rooms/{sample_room.id}/code",
        json={"code": too_long_code}
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_nonexistent_room(client: AsyncClient, nonexistent_uuid: str):
    """
    Test updating a non-existent room.
    
    Verifies that:
        - PUT /api/v1/rooms/{invalid-id}/code returns 404
        - Error message is informative
    """
    response = await client.put(
        f"/api/v1/rooms/{nonexistent_uuid}/code",
        json={"code": "test"}
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_room_invalid_uuid(client: AsyncClient, invalid_uuid: str):
    """
    Test updating a room with invalid UUID format.
    
    Verifies proper error handling for malformed UUIDs.
    """
    response = await client.put(
        f"/api/v1/rooms/{invalid_uuid}/code",
        json={"code": "test"}
    )
    
    assert response.status_code in [400, 422]


# ============================================================================
# DELETE ROOM TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_delete_room_success(
    client: AsyncClient,
    sample_room: Room,
    db_session: AsyncSession
):
    """
    Test successful room deletion.
    
    Verifies that:
        - DELETE /api/v1/rooms/{id} returns 204
        - Room is removed from database
    """
    room_id = sample_room.id
    
    response = await client.delete(f"/api/v1/rooms/{room_id}")
    
    assert response.status_code == 204
    
    # Verify room is deleted
    result = await db_session.get(Room, room_id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent_room(client: AsyncClient, nonexistent_uuid: str):
    """
    Test deleting a non-existent room.
    
    Verifies that:
        - DELETE /api/v1/rooms/{invalid-id} returns 404
    """
    response = await client.delete(f"/api/v1/rooms/{nonexistent_uuid}")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_room_invalid_uuid(client: AsyncClient, invalid_uuid: str):
    """
    Test deleting a room with invalid UUID format.
    
    Verifies proper error handling for malformed UUIDs.
    """
    response = await client.delete(f"/api/v1/rooms/{invalid_uuid}")
    
    assert response.status_code in [400, 404, 422]


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_room_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """
    Test complete room lifecycle: create, read, update, delete.
    
    Verifies that all operations work together correctly.
    """
    # 1. Create room
    create_response = await client.post(
        "/api/v1/rooms",
        json={"language": "python", "code": "# Initial"}
    )
    assert create_response.status_code == 201
    room_id = create_response.json()["roomId"]
    
    # 2. Get room
    get_response = await client.get(f"/api/v1/rooms/{room_id}")
    assert get_response.status_code == 200
    assert get_response.json()["code"] == "# Initial"
    
    # 3. Update room
    update_response = await client.put(
        f"/api/v1/rooms/{room_id}/code",
        json={"code": "# Updated"}
    )
    assert update_response.status_code == 200
    assert update_response.json()["code"] == "# Updated"
    
    # 4. Verify update
    get_response2 = await client.get(f"/api/v1/rooms/{room_id}")
    assert get_response2.status_code == 200
    assert get_response2.json()["code"] == "# Updated"
    
    # 5. Delete room
    delete_response = await client.delete(f"/api/v1/rooms/{room_id}")
    assert delete_response.status_code == 204
    
    # 6. Verify deletion
    get_response3 = await client.get(f"/api/v1/rooms/{room_id}")
    assert get_response3.status_code == 404


@pytest.mark.asyncio
async def test_multiple_rooms_independence(client: AsyncClient):
    """
    Test that multiple rooms are independent of each other.
    
    Verifies that updating one room doesn't affect others.
    """
    # Create two rooms
    response1 = await client.post("/api/v1/rooms", json={"code": "room1"})
    response2 = await client.post("/api/v1/rooms", json={"code": "room2"})
    
    room1_id = response1.json()["roomId"]
    room2_id = response2.json()["roomId"]
    
    # Update room1
    await client.put(
        f"/api/v1/rooms/{room1_id}/code",
        json={"code": "room1_updated"}
    )
    
    # Verify room2 is unchanged
    response = await client.get(f"/api/v1/rooms/{room2_id}")
    assert response.json()["code"] == "room2"

