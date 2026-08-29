"""Read-only backtest summary and running-ROI equity curves."""
from __future__ import annotations

import datetime

import pytest

from tests.factories import (
    add_backtest_match,
    add_backtest_model_result,
    add_backtest_prediction,
    add_backtest_run,
)


def test_summary_404_when_no_run_is_stored(client, db):
    response = client.get("/api/backtest")
    assert response.status_code == 404
    assert "No backtest stored" in response.json()["detail"]


def test_summary_uses_the_latest_run_and_orders_models_by_brier(client, db):
    add_backtest_run(db, id=1, n_matches=1)
    add_backtest_model_result(db, id=1, run_id=1, model="Old", brier=0.10)
    add_backtest_run(db, id=2, n_matches=99, stake=1.0)
    add_backtest_model_result(
        db, id=2, run_id=2, model="Worse", brier=0.25, roi=0.05
    )
    add_backtest_model_result(
        db, id=3, run_id=2, model="Better", brier=0.18, roi=0.11
    )
    add_backtest_model_result(
        db,
        id=4,
        run_id=2,
        model="Bet365 (normalised odds)",
        brier=0.20,
        is_benchmark=True,
        roi=None,
    )

    response = client.get("/api/backtest")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == 2
    assert body["n_matches"] == 99
    assert [row["model"] for row in body["models"]] == [
        "Better",
        "Bet365 (normalised odds)",
        "Worse",
    ]
    assert body["models"][1]["is_benchmark"] is True


def test_equity_404_for_unknown_surface(client, db):
    add_backtest_run(db, id=1)
    add_backtest_match(
        db,
        id=1,
        run_id=1,
        row_index=0,
        match_date=datetime.date(2026, 1, 2),
        surface="Hard",
    )
    response = client.get("/api/backtest/equity", params={"surface": "Clay"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "Clay" in detail
    assert "Hard" in detail


def test_equity_accumulates_profit_and_sorts_by_roi(client, db):
    add_backtest_run(db, id=1, stake=1.0)
    hard_day1 = add_backtest_match(
        db,
        id=1,
        run_id=1,
        row_index=0,
        match_date=datetime.date(2026, 1, 1),
        surface="Hard",
    )
    hard_day2 = add_backtest_match(
        db,
        id=2,
        run_id=1,
        row_index=1,
        match_date=datetime.date(2026, 1, 2),
        surface="Hard",
    )
    clay = add_backtest_match(
        db,
        id=3,
        run_id=1,
        row_index=2,
        match_date=datetime.date(2026, 1, 3),
        surface="Clay",
    )

    # Model A: +2 then -1 on Hard (ROI 0.5), ignored Clay bet, plus a no-bet row
    add_backtest_prediction(
        db,
        id=1,
        run_id=1,
        match_id=hard_day1.id,
        model="A",
        bet_side="player1",
        bet_odds=3.0,
        bet_profit=2.0,
    )
    add_backtest_prediction(
        db,
        id=2,
        run_id=1,
        match_id=hard_day2.id,
        model="A",
        bet_side="player2",
        bet_odds=1.8,
        bet_profit=-1.0,
    )
    add_backtest_prediction(
        db,
        id=3,
        run_id=1,
        match_id=clay.id,
        model="A",
        bet_side="player1",
        bet_odds=2.0,
        bet_profit=1.0,
    )
    add_backtest_prediction(
        db, id=4, run_id=1, match_id=hard_day1.id, model="A", bet_side=None
    )

    # Model B: one losing Hard bet (ROI -1) — should sort below A
    add_backtest_prediction(
        db,
        id=5,
        run_id=1,
        match_id=hard_day1.id,
        model="B",
        bet_side="player1",
        bet_odds=1.5,
        bet_profit=-1.0,
    )

    all_surfaces = client.get("/api/backtest/equity").json()
    assert all_surfaces["run_id"] == 1
    assert all_surfaces["surface"] == "All"
    assert [row["model"] for row in all_surfaces["series"]] == ["A", "B"]

    series_a = all_surfaces["series"][0]
    assert series_a["n_bets"] == 3
    assert series_a["n_wins"] == 2
    assert series_a["profit"] == 2.0
    assert series_a["roi"] == pytest.approx(2.0 / 3.0)
    assert [point["date"] for point in series_a["points"]] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]
    assert series_a["points"][0]["cumulative_profit"] == 2.0
    assert series_a["points"][0]["roi"] == pytest.approx(2.0)
    assert series_a["points"][1]["cumulative_profit"] == 1.0
    assert series_a["points"][1]["cumulative_bets"] == 2
    assert series_a["points"][1]["roi"] == pytest.approx(0.5)

    hard_only = client.get(
        "/api/backtest/equity", params={"surface": "Hard"}
    ).json()
    assert hard_only["surface"] == "Hard"
    hard_a = next(row for row in hard_only["series"] if row["model"] == "A")
    assert hard_a["n_bets"] == 2
    assert hard_a["profit"] == 1.0
    assert hard_a["roi"] == pytest.approx(0.5)
    assert len(hard_a["points"]) == 2
