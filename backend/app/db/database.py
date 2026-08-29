"""Engine and session management for Supabase Postgres."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import DATABASE_URL
from .models import Base

NO_DATABASE = (
    "DATABASE_URL is not set. Supabase Postgres is the only supported "
    "database; there is no local fallback."
)

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        future=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
else:
    engine = None
    SessionLocal = None


def init_db() -> None:
    if engine is None:
        raise RuntimeError(NO_DATABASE)
    Base.metadata.create_all(engine)


def missing_tables() -> list:
    from sqlalchemy import inspect

    if engine is None:
        raise RuntimeError(NO_DATABASE)
    present = set(inspect(engine).get_table_names())
    return sorted(name for name in Base.metadata.tables if name not in present)


def get_session():
    """FastAPI dependency yielding a database session."""
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail=NO_DATABASE)
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
