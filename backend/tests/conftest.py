
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import MODEL_FILENAMES  # noqa: E402
from app.db.models import Base  # noqa: E402


@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def SessionFactory(sqlite_engine):
    return sessionmaker(
        bind=sqlite_engine, autoflush=False, expire_on_commit=False
    )


@pytest.fixture
def db(SessionFactory):
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(SessionFactory):
    """HTTP client against the real app, with DB and model-load isolated."""
    from app.db.database import get_session
    from app.main import app
    from app.services.model_runner import model_runner

    def override_get_session():
        session = SessionFactory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    model_runner.pipelines = {}

    try:
        with (
            patch("app.main.CONFIG_ERRORS", []),
            patch("app.main.missing_tables", return_value=[]),
            patch.object(model_runner, "load"),
            patch("app.main.SessionLocal", SessionFactory),
        ):
            with TestClient(app) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
        model_runner.pipelines = {}


@pytest.fixture
def loaded_models():
    """Mark the singleton runner as fully loaded without opening joblibs."""
    from app.services.model_runner import model_runner

    model_runner.pipelines = {name: object() for name in MODEL_FILENAMES}
    yield
    model_runner.pipelines = {}
