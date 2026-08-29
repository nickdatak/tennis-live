"""Health reports degraded instead of crashing when something is missing."""
from __future__ import annotations

import datetime
from unittest.mock import patch

from tests.factories import add_match_result, add_player


def test_health_ok_when_models_db_and_startup_are_clean(client, db, loaded_models):
    add_player(db, id=1, slug="a", name="A", rank=1.0)
    add_player(db, id=2, slug="b", name="B", rank=2.0)
    add_match_result(
        db,
        id=1,
        winner_id=1,
        loser_id=2,
        date=datetime.date(2026, 6, 15),
    )

    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["models_loaded"] == 6
    assert body["database"] == "connected"
    assert body["players_in_db"] == 2
    assert body["data_through"] == "2026-06-15"
    assert body["startup_errors"] == []


def test_health_degraded_when_models_are_not_loaded(client, db):
    add_player(db, id=1, slug="a", name="A")
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["models_loaded"] == 0


def test_health_degraded_when_database_is_missing(client, loaded_models):
    with patch("app.main.SessionLocal", None):
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"].startswith("error:")
    assert body["players_in_db"] is None


def test_health_degraded_when_startup_recorded_an_error(client, db, loaded_models):
    from app.main import startup_errors

    add_player(db, id=1, slug="a", name="A")
    startup_errors.append("missing tables: players")
    try:
        response = client.get("/api/health")
    finally:
        startup_errors.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert "missing tables: players" in body["startup_errors"]
