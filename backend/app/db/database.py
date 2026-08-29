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
    """Create any missing tables. FOR THE SEEDING SCRIPTS ONLY.

    This issues DDL, so it must never run in the request-serving process: the
    Railway role is read-only, and a server that can reshape its own schema is
    a server that can silently create drift. `create_all` only ever ADDS -- it
    never drops a removed table nor alters a changed column -- so calling it at
    boot let an orphaned `refresh_log` survive in production long after the
    model was deleted. Schema changes belong in the scripts, run deliberately.
    """
    Base.metadata.create_all(engine)


def missing_tables() -> list:
    """Tables the ORM expects but the database does not have. Read-only.

    The boot-time replacement for init_db(): same early warning, no DDL and no
    privileges beyond SELECT. Surfaced through /api/health.
    """
    from sqlalchemy import inspect

    present = set(inspect(engine).get_table_names())
    return sorted(name for name in Base.metadata.tables if name not in present)


def get_session():
    """FastAPI dependency yielding a database session."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
