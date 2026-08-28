"""Engine and session management for Supabase Postgres (or dev SQLite fallback)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import DATA_DIR, DATABASE_URL, USING_DEV_SQLITE
from .models import Base

if USING_DEV_SQLITE:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # read-only serverless filesystem; init_db will surface the error

# One long-lived process (a container, not a per-request function), so a
# real pool is both possible and correct: it is created once and reused for
# the life of the process instead of being rebuilt on every cold start.
# pool_recycle stays modest because the Supabase pooler drops idle sessions.
_pool_kwargs = (
    {}
    if USING_DEV_SQLITE
    else {"pool_size": 5, "max_overflow": 5, "pool_recycle": 300}
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
