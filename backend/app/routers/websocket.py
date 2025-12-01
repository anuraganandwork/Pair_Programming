"""
WebSocket router for real-time collaborative code editing.

This module manages WebSocket connections for rooms, enabling real-time
synchronization of code changes, cursor positions, and user presence.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.room_service import RoomService

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Constants
MAX_CONNECTIONS_PER_ROOM = 10
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes
DEBOUNCE_INTERVAL = 2.0  # Save to DB every 2 seconds max


class ConnectionManager:
    """
    Manages WebSocket connections for collaborative coding rooms.
    
    Maintains active connections per room and handles message broadcasting,
    connection lifecycle, and room state synchronization.
    
    Attributes:
        active_connections: Dictionary mapping room_id to list of WebSocket connections
        user_info: Dictionary mapping WebSocket to user information
        last_save_time: Dictionary tracking last database save time per room
        room_locks: Dictionary of asyncio.Lock objects per room for thread-safety
    """
    
    def __init__(self):
        """Initialize the connection manager."""
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.user_info: Dict[WebSocket, Dict[str, str]] = {}
        self.last_save_time: Dict[str, float] = {}
        self.room_locks: Dict[str, asyncio.Lock] = {}
        logger.info("ConnectionManager initialized")
    
    def _get_room_lock(self, room_id: str) -> asyncio.Lock:
        """
        Get or create a lock for a room.
        
        Args:
            room_id: Room identifier
            
        Returns:
            asyncio.Lock for the room
        """
        if room_id not in self.room_locks:
            self.room_locks[room_id] = asyncio.Lock()
        return self.room_locks[room_id]
    
    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Accept and register a new WebSocket connection.
        
        Accepts the WebSocket connection, adds it to the room's connection list,
        sends initial room state, and broadcasts a user_joined message.
        
        Args:
            websocket: WebSocket connection to register
            room_id: Room ID to join
            user_id: Optional user identifier (generated if not provided)
            
        Returns:
            bool: True if connection successful, False if room is full
        """
        # Generate user_id if not provided
        if not user_id:
            user_id = f"user_{uuid.uuid4().hex[:8]}"
        
        # Check room capacity
        if room_id in self.active_connections:
            if len(self.active_connections[room_id]) >= MAX_CONNECTIONS_PER_ROOM:
                logger.warning(
                    f"Room {room_id} is full ({MAX_CONNECTIONS_PER_ROOM} users). "
                    f"Rejecting connection from {user_id}"
                )
                return False
        
        # Accept WebSocket connection
        await websocket.accept()
        
        # Use lock for thread-safe operations
        lock = self._get_room_lock(room_id)
        async with lock:
            # Add to active connections
            if room_id not in self.active_connections:
                self.active_connections[room_id] = []
            
            self.active_connections[room_id].append(websocket)
            
            # Store user info
            self.user_info[websocket] = {
                "user_id": user_id,
                "room_id": room_id,
                "connected_at": datetime.utcnow().isoformat()
            }
        
        logger.info(
            f"User {user_id} connected to room {room_id}. "
            f"Total connections: {len(self.active_connections[room_id])}"
        )
        
        # Send initial room state
        await self._send_initial_state(websocket, room_id)
        
        # Broadcast user_joined to other users
        await self.broadcast(
            room_id,
            {
                "type": "user_joined",
                "data": {
                    "user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "total_users": len(self.active_connections[room_id])
                },
                "room_id": room_id
            },
            exclude=websocket
        )
        
        return True
    
    async def _send_initial_state(self, websocket: WebSocket, room_id: str):
        """
        Send initial room state to newly connected user.
        
        Args:
            websocket: WebSocket connection
            room_id: Room identifier
        """
        try:
            # Fetch current room state from database
            async with AsyncSessionLocal() as db:
                room = await RoomService.get_room(db, room_id)
                
                if room:
                    await self.send_personal_message(
                        {
                            "type": "initial_state",
                            "data": {
                                "code": room.code or "",
                                "language": room.language,
                                "room_id": room_id,
                                "timestamp": datetime.utcnow().isoformat()
                            },
                            "room_id": room_id
                        },
                        websocket
                    )
                    logger.debug(f"Sent initial state to user in room {room_id}")
                else:
                    logger.warning(f"Room {room_id} not found in database")
                    
        except Exception as e:
            logger.error(f"Error sending initial state for room {room_id}: {e}")
    
    def disconnect(self, websocket: WebSocket, room_id: str):
        """
        Remove a WebSocket connection and clean up.
        
        Removes the connection from active connections, broadcasts a user_left
        message, and cleans up empty room entries.
        
        Args:
            websocket: WebSocket connection to remove
            room_id: Room ID to leave
        """
        user_id = self.user_info.get(websocket, {}).get("user_id", "unknown")
        
        # Remove from active connections
        if room_id in self.active_connections:
            if websocket in self.active_connections[room_id]:
                self.active_connections[room_id].remove(websocket)
                
                # Clean up empty rooms
                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]
                    if room_id in self.room_locks:
                        del self.room_locks[room_id]
                    if room_id in self.last_save_time:
                        del self.last_save_time[room_id]
                    logger.info(f"Room {room_id} is now empty, cleaned up")
        
        # Remove user info
        if websocket in self.user_info:
            del self.user_info[websocket]
        
        logger.info(
            f"User {user_id} disconnected from room {room_id}. "
            f"Remaining connections: {len(self.active_connections.get(room_id, []))}"
        )
        
        # Broadcast user_left message (best effort, don't await)
        try:
            asyncio.create_task(
                self.broadcast(
                    room_id,
                    {
                        "type": "user_left",
                        "data": {
                            "user_id": user_id,
                            "timestamp": datetime.utcnow().isoformat(),
                            "total_users": len(self.active_connections.get(room_id, []))
                        },
                        "room_id": room_id
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error broadcasting user_left: {e}")
    
    async def broadcast(
        self,
        room_id: str,
        message: dict,
        exclude: Optional[WebSocket] = None
    ):
        """
        Broadcast a message to all connections in a room.
        
        Sends the message to all active connections in the specified room,
        optionally excluding one connection (typically the sender).
        Automatically removes broken connections.
        
        Args:
            room_id: Room to broadcast to
            message: Message dictionary to send (will be JSON serialized)
            exclude: Optional WebSocket connection to skip
        """
        if room_id not in self.active_connections:
            return
        
        # Get list of connections (copy to avoid modification during iteration)
        connections = list(self.active_connections[room_id])
        broken_connections = []
        
        # Serialize message once
        try:
            message_json = json.dumps(message)
        except Exception as e:
            logger.error(f"Error serializing message: {e}")
            return
        
        # Send to all connections
        for connection in connections:
            if connection is exclude:
                continue
            
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(
                    f"Error sending to connection in room {room_id}: {e}. "
                    f"Marking for removal."
                )
                broken_connections.append(connection)
        
        # Clean up broken connections
        for connection in broken_connections:
            self.disconnect(connection, room_id)
    
    async def send_personal_message(
        self,
        message: dict,
        websocket: WebSocket
    ):
        """
        Send a message to a specific WebSocket connection.
        
        Args:
            message: Message dictionary to send
            websocket: Target WebSocket connection
        """
        try:
            message_json = json.dumps(message)
            await websocket.send_text(message_json)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    def get_room_connection_count(self, room_id: str) -> int:
        """
        Get the number of active connections in a room.
        
        Args:
            room_id: Room identifier
            
        Returns:
            int: Number of active connections
        """
        return len(self.active_connections.get(room_id, []))
    
    def get_user_id(self, websocket: WebSocket) -> str:
        """
        Get the user ID for a WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            
        Returns:
            str: User ID or "unknown"
        """
        return self.user_info.get(websocket, {}).get("user_id", "unknown")
    
    def should_save_to_db(self, room_id: str) -> bool:
        """
        Check if enough time has passed since last save (debouncing).
        
        Args:
            room_id: Room identifier
            
        Returns:
            bool: True if should save to database
        """
        import time
        current_time = time.time()
        last_save = self.last_save_time.get(room_id, 0)
        
        if current_time - last_save >= DEBOUNCE_INTERVAL:
            self.last_save_time[room_id] = current_time
            return True
        
        return False


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    user_id: Optional[str] = None
):
    """
    WebSocket endpoint for real-time room collaboration.
    
    Handles WebSocket connections for a specific room, enabling real-time
    code synchronization, cursor position updates, and user presence.
    
    Message Types:
        - code_update: Update room code (saves to DB with debouncing)
        - cursor_move: Update cursor position (broadcast only, no DB save)
        - ping: Heartbeat request (responds with pong)
        - user_joined: Broadcast when user connects
        - user_left: Broadcast when user disconnects
        - initial_state: Sent to new connections with current room state
    
    Args:
        websocket: WebSocket connection
        room_id: Room ID to join (path parameter)
        user_id: Optional user identifier (query parameter)
        
    Example Client Usage:
        ```javascript
        const ws = new WebSocket('ws://localhost:8000/ws/room-uuid?user_id=user123');
        
        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            console.log('Received:', message.type);
        };
        
        ws.send(JSON.stringify({
            type: 'code_update',
            data: { code: 'new code here', user_id: 'user123' },
            room_id: 'room-uuid'
        }));
        ```
    """
    logger.info(f"WebSocket connection request for room {room_id} from user {user_id}")
    
    # Verify room exists
    try:
        async with AsyncSessionLocal() as db:
            room = await RoomService.get_room(db, room_id)
            
            if not room:
                logger.warning(f"Room {room_id} not found, rejecting connection")
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Room not found"
                )
                return
    except Exception as e:
        logger.error(f"Error verifying room {room_id}: {e}")
        await websocket.close(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Internal error"
        )
        return
    
    # Connect to room
    connected = await manager.connect(websocket, room_id, user_id)
    
    if not connected:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Room is full (max {MAX_CONNECTIONS_PER_ROOM} users)"
        )
        return
    
    # Get user_id (might have been generated)
    user_id = manager.get_user_id(websocket)
    
    try:
        # Message loop
        while True:
            try:
                # Receive message from client
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=IDLE_TIMEOUT_SECONDS
                )
                
                # Parse message
                try:
                    message = json.loads(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {user_id} in room {room_id}: {e}")
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"message": "Invalid JSON format"},
                            "room_id": room_id
                        },
                        websocket
                    )
                    continue
                
                message_type = message.get("type")
                message_data = message.get("data", {})
                
                logger.debug(
                    f"Received {message_type} from {user_id} in room {room_id}"
                )
                
                # Handle different message types
                if message_type == "code_update":
                    await handle_code_update(
                        room_id, user_id, message_data, websocket
                    )
                
                elif message_type == "cursor_move":
                    await handle_cursor_move(
                        room_id, user_id, message_data, websocket
                    )
                
                elif message_type == "ping":
                    await manager.send_personal_message(
                        {
                            "type": "pong",
                            "data": {"timestamp": datetime.utcnow().isoformat()},
                            "room_id": room_id
                        },
                        websocket
                    )
                
                else:
                    logger.warning(
                        f"Unknown message type '{message_type}' from {user_id}"
                    )
                    
            except asyncio.TimeoutError:
                logger.info(
                    f"Connection timeout for {user_id} in room {room_id} "
                    f"(idle for {IDLE_TIMEOUT_SECONDS}s)"
                )
                break
            
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnect for {user_id} in room {room_id}")
                break
            
            except Exception as e:
                logger.error(
                    f"Error in message loop for {user_id} in room {room_id}: {e}",
                    exc_info=True
                )
                break
    
    finally:
        # Clean up connection
        manager.disconnect(websocket, room_id)
        logger.info(f"Connection closed for {user_id} in room {room_id}")


async def handle_code_update(
    room_id: str,
    user_id: str,
    data: dict,
    sender: WebSocket
):
    """
    Handle code update message.
    
    Updates the room code in the database (with debouncing) and broadcasts
    the change to all other users in the room.
    
    Args:
        room_id: Room identifier
        user_id: User who made the update
        data: Message data containing 'code'
        sender: WebSocket connection of sender
    """
    code = data.get("code", "")
    
    # Validate code length
    if len(code) > 50000:
        logger.warning(
            f"Code too long from {user_id} in room {room_id}: {len(code)} chars"
        )
        await manager.send_personal_message(
            {
                "type": "error",
                "data": {"message": "Code exceeds maximum length of 50,000 characters"},
                "room_id": room_id
            },
            sender
        )
        return
    
    # Broadcast to other users immediately
    await manager.broadcast(
        room_id,
        {
            "type": "code_update",
            "data": {
                "code": code,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            },
            "room_id": room_id
        },
        exclude=sender
    )
    
    # Save to database with debouncing
    if manager.should_save_to_db(room_id):
        try:
            async with AsyncSessionLocal() as db:
                await RoomService.update_room_code(db, room_id, code)
                logger.debug(f"Saved code update for room {room_id} to database")
        except Exception as e:
            logger.error(
                f"Error saving code to database for room {room_id}: {e}",
                exc_info=True
            )


async def handle_cursor_move(
    room_id: str,
    user_id: str,
    data: dict,
    sender: WebSocket
):
    """
    Handle cursor position update.
    
    Broadcasts cursor position to all other users in the room.
    Does not save to database.
    
    Args:
        room_id: Room identifier
        user_id: User who moved cursor
        data: Message data containing 'cursor_position'
        sender: WebSocket connection of sender
    """
    cursor_position = data.get("cursor_position", 0)
    
    # Broadcast cursor position (no DB save)
    await manager.broadcast(
        room_id,
        {
            "type": "cursor_move",
            "data": {
                "cursor_position": cursor_position,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            },
            "room_id": room_id
        },
        exclude=sender
    )

