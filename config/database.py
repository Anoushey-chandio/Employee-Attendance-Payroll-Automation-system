"""SQLAlchemy database engine and session management.

Provides connection pooling, session factory, and database dependency injection.
"""

from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from config.settings import get_settings
from utils.exceptions import DatabaseError
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Create SQLAlchemy engine with connection pooling
if settings.use_local_sqlite:
    # SQLite for testing (no pooling needed)
    engine = create_engine(
        "sqlite:///./payroll_system.db",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
        echo=settings.app_env == "development"
    )
    logger.info("Using SQLite database for testing")
else:
    # PostgreSQL with connection pooling
    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,  # Verify connections before using
        echo=settings.app_env == "development",
        poolclass=QueuePool
    )
    logger.info("Connected to PostgreSQL database with connection pooling")


# Enable foreign key constraints for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable foreign key constraints for SQLite connections."""
    if settings.use_local_sqlite:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency for dependency injection.

    Yields:
        SQLAlchemy session instance

    Raises:
        DatabaseError: If database connection fails
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise DatabaseError(
            "Database operation failed",
            details={"error": str(e)}
        )
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database tables.

    Creates all tables defined in SQLAlchemy models.
    Should be called once during application startup.
    """
    try:
        from models.base import Base
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise DatabaseError(
            "Failed to initialize database tables",
            details={"error": str(e)}
        )


def check_db_connection() -> bool:
    """
    Check if database connection is alive.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {str(e)}")
        return False
