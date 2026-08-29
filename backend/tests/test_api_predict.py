"""Predict endpoint: lookup, validation, H2H display, and response shape."""
from __future__ import annotations

import datetime
from unittest.mock import patch

from app.config import MODEL_FEATURE_COLUMNS, MODEL_FILENAMES
from tests.factories import add_match_result, add_player


def _seed_pair(db):
    add_player(
        db,
        id=1,
        slug="alcaraz-c",
        name="Alcaraz C.",
        rank=1.0,
        elo_global=2200.0,
    )
    add_player(
        db,
        id=2,
        slug="sinner-j",
        name="Sinner J.",
        rank=2.0,
        elo_global=2180.0,
    )
    add_match_result(
        db, id=1, winner_id=1, loser_id=2, date=datetime.date(2025, 6, 1)
    )
    add_match_result(
        db, id=2, winner_id=1, loser_id=2, date=datetime.date(2026, 1, 10)
    )
    add_match_result(
        db, id=3, winner_id=2, loser_id=1, date=datetime.date(2026, 3, 4)
    )


def _predict_payload(**overrides):
    body = {"player1": "Alcaraz C.", "player2": "Sinner J.", "surface": "Hard"}
    body.update(overrides)
    return body


def test_predict_503_when_models_are_not_loaded(client, db):
    _seed_pair(db)
    response = client.post("/api/predict", json=_predict_payload())
    assert response.status_code == 503
    assert "not loaded" in response.json()["detail"]


def test_predict_404_for_unknown_player(client, db, loaded_models):
    _seed_pair(db)
    response = client.post(
        "/api/predict", json=_predict_payload(player2="Nobody")
    )
    assert response.status_code == 404
    assert "Nobody" in response.json()["detail"]


def test_predict_400_when_both_identifiers_are_the_same_player(
    client, db, loaded_models
):
    _seed_pair(db)
    response = client.post(
        "/api/predict",
        json=_predict_payload(player1="Alcaraz C.", player2="alcaraz-c"),
    )
    assert response.status_code == 400
    assert "different players" in response.json()["detail"]


def test_predict_422_for_invalid_surface_or_empty_name(client, db, loaded_models):
    _seed_pair(db)
    assert (
        client.post(
            "/api/predict", json=_predict_payload(surface="Carpet")
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/predict", json=_predict_payload(player1="")
        ).status_code
        == 422
    )


def test_predict_ok_shape_h2h_and_features_exclude_h2h(
    client, db, loaded_models
):
    _seed_pair(db)
    stub = {
        "per_model": {name: 0.61 for name in MODEL_FILENAMES},
        "mean": 0.61,
        "features_player1_first": {column: 1.0 for column in MODEL_FEATURE_COLUMNS},
    }
    with patch(
        "app.api.predict.model_runner.predict", return_value=stub
    ) as mocked:
        response = client.post("/api/predict", json=_predict_payload())

    assert response.status_code == 200
    body = response.json()
    mocked.assert_called_once()
    assert body["player1"]["slug"] == "alcaraz-c"
    assert body["player2"]["slug"] == "sinner-j"
    assert body["surface"] == "Hard"
    assert len(body["predictions"]) == 6
    assert body["mean_player1_win_probability"] == 0.61
    assert set(body["features_player1_first"]) == set(MODEL_FEATURE_COLUMNS)
    assert "head_to_head" not in body["features_player1_first"]
    assert body["head_to_head"] == {
        "player1_wins": 2,
        "player2_wins": 1,
        "since": "2025-06-01",
    }


def test_predict_h2h_is_zero_when_the_pair_has_never_met(
    client, db, loaded_models
):
    add_player(db, id=1, slug="a", name="A", rank=1.0)
    add_player(db, id=2, slug="b", name="B", rank=2.0)
    stub = {
        "per_model": {name: 0.5 for name in MODEL_FILENAMES},
        "mean": 0.5,
        "features_player1_first": {column: 0.0 for column in MODEL_FEATURE_COLUMNS},
    }
    with patch("app.api.predict.model_runner.predict", return_value=stub):
        response = client.post(
            "/api/predict",
            json={"player1": "A", "player2": "B", "surface": "Grass"},
        )
    assert response.status_code == 200
    assert response.json()["head_to_head"] == {
        "player1_wins": 0,
        "player2_wins": 0,
        "since": None,
    }
