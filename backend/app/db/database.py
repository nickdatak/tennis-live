"""Engine and session management for Supabase Postgres (or dev SQLite fallback)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import DATA_DIR, DATABASE_URL, USING_DEV_SQLITE
from .models import Base

if USING_DEV_SQLITE:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

# Small pool + recycle: friendly to serverless instances talking to the
# Supabase pooler (harmless for local SQLite).
_pool_kwargs = (
    {}
    if USING_DEV_SQLITE
    else {"pool_size": 2, "max_overflow": 3, "pool_recycle": 300}
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables if they don't exist (idempotent)."""
    Base.metadata.create_all(engine)


def get_session():
    """FastAPI dependency yielding a database session."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
