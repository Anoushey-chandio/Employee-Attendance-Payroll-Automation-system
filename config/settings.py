"""Application settings and environment variable management.

Uses Pydantic Settings for type-safe configuration loading.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Database Configuration
    database_url: str = Field(
        ...,
        description="PostgreSQL connection string for Supabase"
    )

    # Supabase Configuration
    supabase_url: str = Field(
        ...,
        description="Supabase project URL"
    )
    supabase_key: str = Field(
        ...,
        description="Supabase anon/public key"
    )

    # Application Security
    secret_key: str = Field(
        ...,
        description="Secret key for session management and encryption"
    )

    # Application Environment
    app_env: Literal["development", "staging", "production"] = Field(
        default="production",
        description="Application environment mode"
    )

    use_local_sqlite: bool = Field(
        default=False,
        description="Use local SQLite instead of Supabase (for testing)"
    )

    # Database Connection Pool Settings
    db_pool_size: int = Field(
        default=5,
        description="Database connection pool size"
    )
    db_max_overflow: int = Field(
        default=10,
        description="Maximum overflow connections beyond pool_size"
    )
    db_pool_timeout: int = Field(
        default=30,
        description="Timeout in seconds for getting a connection from pool"
    )
    db_pool_recycle: int = Field(
        default=3600,
        description="Recycle connections after this many seconds"
    )

    # Business Rules Configuration
    regular_hours_cap: float = Field(
        default=8.0,
        description="Maximum regular hours per day before overtime"
    )
    overtime_hours_cap: float = Field(
        default=4.0,
        description="Maximum overtime hours per day"
    )
    overtime_multiplier: float = Field(
        default=1.5,
        description="Overtime pay rate multiplier"
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Application logging level"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings instance.

    Returns:
        Settings instance loaded from environment variables
    """
    return Settings()
