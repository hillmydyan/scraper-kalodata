"""
Database engine and session management.
Supports PostgreSQL (production) with automatic table initialization and quick SQLite fallback for local development.
"""

from typing import Generator
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.models.entities import Base

logger = structlog.get_logger(__name__)

db_url = settings.DATABASE_URL
connect_args = {}

def get_configured_engine():
    if db_url.startswith("sqlite"):
        return create_engine(db_url, connect_args={"check_same_thread": False})
    
    # Try connecting to PostgreSQL with 2-second timeout
    try:
        pg_engine = create_engine(
            db_url,
            connect_args={"connect_timeout": 2},
            pool_pre_ping=True
        )
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Connected successfully to PostgreSQL", url=db_url)
        return pg_engine
    except Exception as ex:
        dev_sqlite = f"sqlite:///{settings.RUNTIME_DIR}/kalodata_dev.db"
        logger.warning(
            "PostgreSQL server not reachable at 127.0.0.1:5433, falling back to local SQLite",
            fallback=dev_sqlite,
            reason=str(ex)
        )
        return create_engine(dev_sqlite, connect_args={"check_same_thread": False})

engine = get_configured_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency / context manager generator for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initializes database schema."""
    Base.metadata.create_all(bind=engine)
