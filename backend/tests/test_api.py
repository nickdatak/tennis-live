"""Integration tests against the real synced models and the seeded dev database.

Prerequisites (both are one-time and idempotent):
    python3 backend/scripts/sync_models.py
    python3 backend/scripts/load_players.py
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:  # triggers lifespan: DB init + model load
        yield test_client


def test_health(client):
    data = client.get("/api/health").json()
    assert data["models_loaded"] == 6
    assert data["database"] == "connected"
    assert data["players_in_db"] > 0


def test_player_search(client):
    data = client.get("/api/players", params={"q": "alcaraz"}).json()
    names = [p["name"] for p in data["players"]]
    assert "Alcaraz C." in names


def test_player_search_empty_query_returns_ranked_players(client):
    data = client.get("/api/players").json()
    assert len(data["players"]) > 0
    ranks = [p["rank"] for p in data["players"] if p["rank"] is not None]
    assert ranks == sorted(ranks)


def test_predict_returns_six_models_and_mean(client):
    response = client.post(
        "/api/predict",
        json={"player1": "Alcaraz C.", "player2": "Djokovic N.", "surface": "Hard"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["predictions"]) == 6
    probabilities = [p["player1_win_probability"] for p in data["predictions"]]
    assert all(0.0 < p < 1.0 for p in probabilities)
    assert abs(data["mean_player1_win_probability"] - sum(probabilities) / 6) < 1e-12
    assert set(data["features_player1_first"]) == {
        "GlobalEloDiff",
        "SurfaceEloDiff",
        "RankDiff",
        "Player1LayoffOver6Months",
        "Player2LayoffOver6Months",
        "MatchesLast7DaysDiff",
    }


def test_predict_is_orientation_symmetric(client):
    forward = client.post(
        "/api/predict",
        json={"player1": "Alcaraz C.", "player2": "Djokovic N.", "surface": "Clay"},
    ).json()
    reverse = client.post(
        "/api/predict",
        json={"player1": "Djokovic N.", "player2": "Alcaraz C.", "surface": "Clay"},
    ).json()
    assert (
        pytest.approx(forward["mean_player1_win_probability"], abs=1e-12)
        == 1.0 - reverse["mean_player1_win_probability"]
    )


def test_predict_case_insensitive_and_slug_lookup(client):
    response = client.post(
        "/api/predict",
        json={"player1": "alcaraz c.", "player2": "djokovic_n", "surface": "Grass"},
    )
    assert response.status_code == 200


def test_predict_unknown_player_404(client):
    response = client.post(
        "/api/predict",
        json={"player1": "Nobody X.", "player2": "Alcaraz C.", "surface": "Hard"},
    )
    assert response.status_code == 404
    assert "Nobody X." in response.json()["detail"]


def test_predict_same_player_400(client):
    response = client.post(
        "/api/predict",
        json={"player1": "Alcaraz C.", "player2": "Alcaraz C.", "surface": "Hard"},
    )
    assert response.status_code == 400


def test_predict_invalid_surface_422(client):
    response = client.post(
        "/api/predict",
        json={"player1": "Alcaraz C.", "player2": "Djokovic N.", "surface": "Carpet"},
    )
    assert response.status_code == 422


def test_bets_placeholders(client):
    assert client.get("/api/bets").json()["status"] == "not_implemented"
    assert client.post("/api/bets").status_code == 501


def test_frontend_served_at_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Tennis Live" in response.text


def test_refresh_requires_token_when_configured(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "REFRESH_TOKEN", "secret-token")
    assert client.post("/api/refresh").status_code == 401
    assert (
        client.post("/api/refresh", headers={"X-Refresh-Token": "wrong"}).status_code
        == 401
    )
