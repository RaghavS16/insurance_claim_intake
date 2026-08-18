"""
SQLAlchemy database session management and engine initialization.
Supports PostgreSQL for production/docker, and SQLite for zero-config local runs and testing.

Production hardening:
- Connection pool configuration (pool_size, max_overflow, pool_recycle)
- Proper pool disposal support for graceful shutdown
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

DATABASE_URL = settings.DATABASE_URL

# SQLite requires check_same_thread=False and does not support pooling configuration
_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# Connection pool configuration for production PostgreSQL
_pool_kwargs = {}
if not _is_sqlite:
    _pool_kwargs = {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": True,  # Verify connections before use (handles stale connections)
    }

engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Yield a database session and safely close upon request completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def dispose_engine():
    """Dispose of the engine's connection pool. Call on application shutdown."""
    engine.dispose()
    logger.info("Database engine connection pool disposed.")