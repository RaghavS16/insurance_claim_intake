"""
SQLAlchemy database session management and engine initialization.
Supports PostgreSQL for production/docker, and SQLite for zero-config local runs and testing.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

DATABASE_URL = settings.DATABASE_URL

# SQLite requires check_same_thread=False
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Yield a database session and safely close upon request completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()