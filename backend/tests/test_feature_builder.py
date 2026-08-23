"""Unit tests: feature semantics must mirror research/02_feature_creation.ipynb."""
from __future__ import annotations

import datetime

import numpy as np
import pytest

from app.config import MODEL_FEATURE_COLUMNS
from app.services.feature_builder import PlayerState, build_feature_frame


def make_player(**overrides) -> PlayerState:
    defaults = dict(
        name="Test P.",
        elo_global=1600.0,
        surface_elos={"Hard": 1580.0, "Clay": 1550.0, "Grass": 1520.0},
        surface_match_counts={"Hard": 10, "Clay": 5, "Grass": 2},
        rank=20.0,
        last_match_date=datetime.date(2026, 8, 10),
        recent_match_dates=[],
    )
    defaults.update(overrides)
    return PlayerState(**defaults)


PREDICTION_DATE = datetime.date(2026, 8, 24)


class TestWorkloadWindow:
    def test_boundary_exactly_7_days_ago_counts(self):
        player = make_player(recent_match_dates=[PREDICTION_DATE - datetime.timedelta(days=7)])
        assert player.matches_last_7_days(PREDICTION_DATE) == 1

    def test_8_days_ago_does_not_count(self):
        player = make_player(recent_match_dates=[PREDICTION_DATE - datetime.timedelta(days=8)])
        assert player.matches_last_7_days(PREDICTION_DATE) == 0

    def test_prediction_day_itself_does_not_count(self):
        player = make_player(recent_match_dates=[PREDICTION_DATE])
        assert player.matches_last_7_days(PREDICTION_DATE) == 0

    def test_same_day_duplicates_both_count(self):
        date = PREDICTION_DATE - datetime.timedelta(days=2)
        player = make_player(recent_match_dates=[date, date])
        assert player.matches_last_7_days(PREDICTION_DATE) == 2


class TestLayoff:
    def test_exactly_6_months_is_not_layoff(self):
        player = make_player(last_match_date=datetime.date(2026, 2, 24))
        assert player.layoff_over_6_months(PREDICTION_DATE) is False

    def test_6_months_and_a_day_is_layoff(self):
        player = make_player(last_match_date=datetime.date(2026, 2, 23))
        assert player.layoff_over_6_months(PREDICTION_DATE) is True

    def test_unknown_history_is_none(self):
        player = make_player(last_match_date=None)
        assert player.layoff_over_6_months(PREDICTION_DATE) is None


class TestSurfaceDebutElo:
    def test_played_surface_uses_stored_value(self):
        player = make_player()
        assert player.surface_elo("Hard") == 1580.0

    def test_unplayed_surface_falls_back_to_1500(self):
        # Default mode is "initial" (training semantics).
        player = make_player(
            surface_elos={"Hard": 1580.0, "Clay": 1600.0, "Grass": 1600.0},
            surface_match_counts={"Hard": 10, "Clay": 0, "Grass": 0},
        )
        assert player.surface_elo("Clay") == 1500.0


class TestFeatureFrame:
    def test_contract_columns_and_orientation_mirror(self):
        p1 = make_player(elo_global=1700.0, rank=5.0)
        p2 = make_player(
            name="Other P.",
            elo_global=1600.0,
            rank=15.0,
            last_match_date=datetime.date(2025, 12, 1),  # layoff True
        )
        frame = build_feature_frame(p1, p2, "Hard", PREDICTION_DATE)

        assert frame.columns.tolist() == MODEL_FEATURE_COLUMNS
        assert len(frame) == 2
        assert frame.loc[0, "GlobalEloDiff"] == 100.0
        assert frame.loc[1, "GlobalEloDiff"] == -100.0
        assert frame.loc[0, "RankDiff"] == -10.0
        assert frame.loc[1, "RankDiff"] == 10.0
        # Layoff flags swap between orientations.
        assert frame.loc[0, "Player1LayoffOver6Months"] == 0.0
        assert frame.loc[0, "Player2LayoffOver6Months"] == 1.0
        assert frame.loc[1, "Player1LayoffOver6Months"] == 1.0
        assert frame.loc[1, "Player2LayoffOver6Months"] == 0.0

    def test_missing_rank_gives_nan_not_zero(self):
        p1 = make_player(rank=None)
        p2 = make_player(name="Other P.")
        frame = build_feature_frame(p1, p2, "Hard", PREDICTION_DATE)
        assert np.isnan(frame.loc[0, "RankDiff"])
        assert np.isnan(frame.loc[1, "RankDiff"])

    def test_workload_diff(self):
        recent = [PREDICTION_DATE - datetime.timedelta(days=d) for d in (1, 2, 3)]
        p1 = make_player(recent_match_dates=recent)
        p2 = make_player(name="Other P.", recent_match_dates=recent[:1])
        frame = build_feature_frame(p1, p2, "Hard", PREDICTION_DATE)
        assert frame.loc[0, "MatchesLast7DaysDiff"] == 2.0
        assert frame.loc[1, "MatchesLast7DaysDiff"] == -2.0

    def test_rejects_unknown_surface(self):
        p1 = make_player()
        p2 = make_player(name="Other P.")
        with pytest.raises(AssertionError):
            build_feature_frame(p1, p2, "Carpet", PREDICTION_DATE)
