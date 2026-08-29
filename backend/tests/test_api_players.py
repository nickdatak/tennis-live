"""Player search, full list, and surface-specific comparison."""
from __future__ import annotations

from tests.factories import add_player


def _seed_players(db):
    add_player(
        db,
        id=1,
        slug="alcaraz-c",
        name="Alcaraz C.",
        rank=1.0,
        elo_global=2200.0,
        elo_hard=2180.0,
        elo_clay=2210.0,
        elo_grass=2100.0,
        matches_global=80,
        matches_hard=40,
        matches_clay=30,
        matches_grass=10,
    )
    add_player(
        db,
        id=2,
        slug="djokovic-n",
        name="Djokovic N.",
        rank=2.0,
        elo_global=2150.0,
        elo_hard=2140.0,
        elo_clay=2120.0,
        elo_grass=2160.0,
    )
    add_player(db, id=3, slug="qualifier-q", name="Qualifier Q.", rank=None)


def test_search_is_case_insensitive_substring(client, db):
    _seed_players(db)
    response = client.get("/api/players", params={"q": "alcar"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "alcar"
    assert [row["slug"] for row in body["players"]] == ["alcaraz-c"]


def test_search_matches_slug(client, db):
    _seed_players(db)
    response = client.get("/api/players", params={"q": "djokovic-n"})
    assert response.status_code == 200
    assert [row["slug"] for row in response.json()["players"]] == ["djokovic-n"]


def test_search_empty_query_returns_ranked_players_first(client, db):
    _seed_players(db)
    response = client.get("/api/players", params={"q": "  ", "limit": 10})
    assert response.status_code == 200
    slugs = [row["slug"] for row in response.json()["players"]]
    assert slugs == ["alcaraz-c", "djokovic-n", "qualifier-q"]


def test_search_limit_is_validated(client, db):
    assert client.get("/api/players", params={"limit": 0}).status_code == 422
    assert client.get("/api/players", params={"limit": 51}).status_code == 422


def test_all_players_returns_the_full_ranked_list(client, db):
    _seed_players(db)
    response = client.get("/api/players/all")
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == ""
    assert [row["name"] for row in body["players"]] == [
        "Alcaraz C.",
        "Djokovic N.",
        "Qualifier Q.",
    ]


def test_compare_uses_the_requested_surface_elo_and_matches(client, db):
    _seed_players(db)
    response = client.get(
        "/api/players/compare",
        params={"player1": "Alcaraz C.", "player2": "djokovic-n", "surface": "Clay"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["surface"] == "Clay"
    assert body["player1"]["elo_surface"] == 2210.0
    assert body["player1"]["matches_surface"] == 30
    assert body["player2"]["elo_surface"] == 2120.0


def test_compare_rejects_the_same_player_by_name_and_slug(client, db):
    _seed_players(db)
    response = client.get(
        "/api/players/compare",
        params={"player1": "Alcaraz C.", "player2": "alcaraz-c", "surface": "Hard"},
    )
    assert response.status_code == 400
    assert "different players" in response.json()["detail"]


def test_compare_404_for_unknown_player(client, db):
    _seed_players(db)
    response = client.get(
        "/api/players/compare",
        params={"player1": "Alcaraz C.", "player2": "Nobody", "surface": "Hard"},
    )
    assert response.status_code == 404


def test_compare_rejects_unknown_surface(client, db):
    response = client.get(
        "/api/players/compare",
        params={"player1": "A", "player2": "B", "surface": "Carpet"},
    )
    assert response.status_code == 422
