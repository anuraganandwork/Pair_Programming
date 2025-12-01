"""
Application configuration settings using pydantic-settings.

This module manages all environment variables and application settings,
including database, CORS, WebSocket, and room management configurations.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Try to load .env file manually with proper error handling
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except (ImportError, PermissionError, OSError):
    # If .env can't be loaded, just use system environment variables
    pass


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden using environment variables or a .env file.
    """
    
    # Database Configuration
    database_url: str = Field(
        ...,
        description="PostgreSQL database URL with asyncpg driver"
    )
    
    # Environment
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production)"
    )
    
    # CORS Configuration
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed CORS origins"
    )
    
    # WebSocket Configuration
    websocket_heartbeat_interval: int = Field(
        default=30,
        description="WebSocket heartbeat interval in seconds"
    )
    
    websocket_max_connections_per_room: int = Field(
        default=50,
        description="Maximum number of concurrent WebSocket connections per room"
    )
    
    websocket_message_max_size: int = Field(
        default=1024 * 1024,  # 1MB
        description="Maximum WebSocket message size in bytes"
    )
    
    # Room Management Configuration
    room_max_age_hours: int = Field(
        default=24,
        description="Maximum age of inactive rooms in hours before cleanup"
    )
    
    room_cleanup_interval_minutes: int = Field(
        default=60,
        description="Interval for running room cleanup task in minutes"
    )
    
    # Application Settings
    app_title: str = Field(
        default="Pair Programming API",
        description="API title shown in documentation"
    )
    
    app_version: str = Field(
        default="1.0.0",
        description="API version"
    )
    
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    
    model_config = SettingsConfigDict(
        # Load from environment variables directly
        # Users can manually load .env using: export $(cat .env | xargs)
        case_sensitive=False,
        extra="ignore",
    )
    
    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> List[str]:
        """Parse comma-separated CORS origins into a list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        allowed = ["development", "staging", "production", "test"]
        if v.lower() not in allowed:
            raise ValueError(f"Environment must be one of: {', '.join(allowed)}")
        return v.lower()
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Uses lru_cache to ensure settings are loaded only once
    and reused throughout the application lifecycle.
    
    Returns:
        Settings: Application settings instance
    """
    return Settings()

