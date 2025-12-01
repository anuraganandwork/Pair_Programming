"""
Pydantic schemas for request/response validation.

This module defines all data validation schemas using Pydantic v2,
including request models, response models, and WebSocket message formats.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


# Supported programming languages
SUPPORTED_LANGUAGES = ["python", "javascript", "typescript", "java"]


class RoomCreate(BaseModel):
    """
    Schema for creating a new room.
    
    When creating a room, all fields are optional and will use defaults:
    - code: empty/null
    - language: "python"
    - timestamps: auto-generated
    
    This is intentionally minimal to make room creation simple.
    """
    
    language: Optional[str] = Field(
        default="python",
        description="Programming language for the room",
        examples=["python", "javascript", "typescript", "java"]
    )
    
    code: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="Initial code content (optional)",
        examples=["print('Hello, World!')"]
    )
    
    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> str:
        """
        Validate that the language is supported.
        
        Args:
            v: Language string to validate
            
        Returns:
            str: Validated language string (lowercase)
            
        Raises:
            ValueError: If language is not supported
        """
        if v is None:
            return "python"
        
        v_lower = v.lower()
        if v_lower not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Language must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        return v_lower
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "language": "python",
                    "code": "def hello():\n    print('Hello, World!')"
                },
                {
                    "language": "javascript",
                    "code": "console.log('Hello, World!');"
                }
            ]
        }
    )


class RoomResponse(BaseModel):
    """
    Schema for room response data.
    
    This is returned when fetching room information or after creating/updating a room.
    All fields are required in responses.
    
    Attributes:
        id: Unique room identifier (UUID)
        code: Current code content (can be null/empty)
        language: Programming language
        created_at: When the room was created
        updated_at: When the room was last modified
    """
    
    id: UUID = Field(
        description="Unique room identifier",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    
    code: Optional[str] = Field(
        default=None,
        description="Current code content in the room",
        examples=["print('Hello, World!')"]
    )
    
    language: str = Field(
        description="Programming language",
        examples=["python"]
    )
    
    created_at: datetime = Field(
        description="Timestamp when room was created"
    )
    
    updated_at: datetime = Field(
        description="Timestamp when room was last updated"
    )
    
    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy models
        json_schema_extra={
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "code": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
                    "language": "python",
                    "created_at": "2025-11-30T10:30:00Z",
                    "updated_at": "2025-11-30T11:45:00Z"
                }
            ]
        }
    )


class CodeUpdate(BaseModel):
    """
    Schema for code update operations.
    
    Used when a user updates the code in a room, either via REST API
    or WebSocket. Optionally includes user_id for tracking who made the change.
    
    Attributes:
        code: The new code content (max 50,000 characters)
        user_id: Optional identifier for the user making the change
    """
    
    code: str = Field(
        max_length=50000,
        description="Updated code content (max 50,000 characters)",
        examples=["print('Updated code')"]
    )
    
    user_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional user identifier for tracking changes",
        examples=["user_123", "anonymous_456"]
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "function greet(name) {\n  console.log(`Hello, ${name}!`);\n}",
                    "user_id": "user_123"
                }
            ]
        }
    )


class WebSocketMessage(BaseModel):
    """
    Schema for WebSocket messages.
    
    All WebSocket communication uses this format. The 'type' field determines
    what kind of message it is, and 'data' contains the type-specific payload.
    
    Message Types:
        - "join": User joins a room
        - "leave": User leaves a room
        - "code_update": Code content changed
        - "cursor_move": User cursor position changed
        - "ping": Heartbeat message
        - "pong": Heartbeat response
    
    Attributes:
        type: Message type identifier
        data: Message-specific data payload
        room_id: Optional room identifier (required for most message types)
    """
    
    type: Literal[
        "join", "leave", "code_update", "cursor_move", "ping", "pong"
    ] = Field(
        description="Type of WebSocket message",
        examples=["code_update"]
    )
    
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Message payload (structure varies by type)",
        examples=[{"code": "print('hello')", "user_id": "user_123"}]
    )
    
    room_id: Optional[str] = Field(
        default=None,
        description="Room identifier (required for most message types)",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "code_update",
                    "data": {
                        "code": "console.log('Hello from WebSocket!');",
                        "user_id": "user_123"
                    },
                    "room_id": "550e8400-e29b-41d4-a716-446655440000"
                },
                {
                    "type": "join",
                    "data": {"user_id": "user_123", "username": "Alice"},
                    "room_id": "550e8400-e29b-41d4-a716-446655440000"
                }
            ]
        }
    )


class AutocompleteRequest(BaseModel):
    """
    Schema for code autocomplete requests.
    
    Used to request AI-powered code suggestions based on current code context
    and cursor position.
    
    Attributes:
        code: Current code content
        cursor_position: Character position of cursor in the code (0-indexed)
        language: Programming language for context-aware suggestions
    """
    
    code: str = Field(
        max_length=50000,
        description="Current code content",
        examples=["def fibonacci("]
    )
    
    cursor_position: int = Field(
        ge=0,
        description="Cursor position in the code (0-indexed character offset)",
        examples=[14]
    )
    
    language: str = Field(
        default="python",
        description="Programming language for suggestions",
        examples=["python", "javascript"]
    )
    
    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """
        Validate that the language is supported.
        
        Args:
            v: Language string to validate
            
        Returns:
            str: Validated language string (lowercase)
            
        Raises:
            ValueError: If language is not supported
        """
        v_lower = v.lower()
        if v_lower not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Language must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        return v_lower
    
    @field_validator("cursor_position")
    @classmethod
    def validate_cursor_position(cls, v: int, info) -> int:
        """
        Validate cursor position is within code bounds.
        
        Args:
            v: Cursor position to validate
            info: Validation context with other field values
            
        Returns:
            int: Validated cursor position
            
        Raises:
            ValueError: If cursor position is invalid
        """
        if v < 0:
            raise ValueError("Cursor position must be >= 0")
        
        # Note: We can't validate against code length here because
        # validators run in order and code might not be available yet
        # The route handler should do this validation
        
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "def fibonacci(n):\n    if n <= ",
                    "cursor_position": 31,
                    "language": "python"
                }
            ]
        }
    )


class AutocompleteResponse(BaseModel):
    """
    Schema for code autocomplete responses.
    
    Returns a code suggestion with a confidence score indicating how
    confident the autocomplete engine is in the suggestion.
    
    Attributes:
        suggestion: The suggested code completion
        confidence: Confidence score (0.0 to 1.0)
    """
    
    suggestion: str = Field(
        description="Suggested code completion",
        examples=["1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"]
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the suggestion (0.0 to 1.0)",
        examples=[0.92]
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "suggestion": "1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
                    "confidence": 0.92
                },
                {
                    "suggestion": "name) {\n  console.log(`Hello, ${name}!`);\n}",
                    "confidence": 0.85
                }
            ]
        }
    )

