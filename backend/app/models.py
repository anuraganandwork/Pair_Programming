"""
SQLAlchemy ORM models for the pair programming application.

This module defines the database schema using SQLAlchemy 2.0 declarative
mapping with modern Mapped and mapped_column types.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Room(Base):
    """
    Room model representing a collaborative coding session.
    
    A room is a virtual space where multiple users can collaborate on code
    in real-time. Each room has its own code content, programming language,
    and tracks creation/modification timestamps.
    
    Attributes:
        id: Unique identifier for the room (UUID v4)
        code: The current code content in the room (up to 50,000 characters)
        language: Programming language being used (default: "python")
        created_at: Timestamp when the room was created
        updated_at: Timestamp when the room was last modified
    """
    
    __tablename__ = "rooms"
    
    # Primary key - UUID for better distribution and security
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for the room"
    )
    
    # Code content - nullable to allow empty rooms
    code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Current code content in the room (max 50,000 characters)"
    )
    
    # Programming language
    language: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="python",
        doc="Programming language (python, javascript, typescript, java)"
    )
    
    # Timestamps with server-side defaults
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when the room was created"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        doc="Timestamp when the room was last modified"
    )
    
    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_rooms_created_at", "created_at"),
        Index("ix_rooms_updated_at", "updated_at"),
        Index("ix_rooms_language", "language"),
    )
    
    def __repr__(self) -> str:
        """
        String representation of Room for debugging.
        
        Returns:
            str: Human-readable representation of the room
        """
        return (
            f"<Room(id={self.id}, "
            f"language={self.language!r}, "
            f"code_length={len(self.code) if self.code else 0}, "
            f"created_at={self.created_at.isoformat()})>"
        )

