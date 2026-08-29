"""Training-faithful feature contract: workload, layoff, debut Elo, swap."""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.config import INITIAL_ELO, MODEL_FEATURE_COLUMNS
from app.services import feature_builder
from app.services.feature_builder import (
    NEGATED_COLUMNS,
    SWAPPED_COLUMNS,
    PlayerState,
    build_feature_frame,
    swap_orientation,
)


def make_player(**overrides) -> PlayerState:
    values = dict(
        name="Player",
        elo_global=1800.0,
        surface_elos={"Hard": 1750.0, "Clay": 1650.0, "Grass": 1900.0},
        surface_match_counts={"Hard": 10, "Clay": 4, "Grass": 0},
        rank=5.0,
        last_match_date=datetime.date(2026, 8, 1),
        recent_match_dates=[],
    )
    values.update(overrides)
    return PlayerState(**values)

PREDICTION_DATE = datetime.date(2026, 8, 29)


@pytest.fixture(autouse=True)
def debut_mode_initial(monkeypatch):
    monkeypatch.setattr(feature_builder, "SURFACE_DEBUT_ELO_MODE", "initial")


class TestMatchesLast7Days:
    def test_window_includes_the_seventh_day_back_not_prediction_day(self):
        player = make_player(
            recent_match_dates=[
                datetime.date(2026, 8, 21),  # day before cutoff
                datetime.date(2026, 8, 22),  # cutoff: counts
                datetime.date(2026, 8, 28),
                datetime.date(2026, 8, 29),  # prediction day: never counts
            ]
        )
        assert player.matches_last_7_days(PREDICTION_DATE) == 2

    def test_same_day_duplicates_each_count(self):
        player = make_player(
            recent_match_dates=[
                datetime.date(2026, 8, 25),
                datetime.date(2026, 8, 25),
            ]
        )
        assert player.matches_last_7_days(PREDICTION_DATE) == 2

    def test_empty_history_is_zero(self):
        assert make_player().matches_last_7_days(PREDICTION_DATE) == 0


class TestLayoffOver6Months:
    def test_unknown_when_no_prior_match(self):
        player = make_player(last_match_date=None)
        assert player.layoff_over_6_months(PREDICTION_DATE) is None

    def test_threshold_day_is_not_yet_a_layoff(self):
        last = datetime.date(2026, 2, 28)
        threshold = (
            pd.Timestamp(last) + pd.DateOffset(months=6)
        ).date()
        player = make_player(last_match_date=last)
        assert player.layoff_over_6_months(threshold) is False
        assert player.layoff_over_6_months(
            threshold + datetime.timedelta(days=1)
        ) is True

    def test_uses_calendar_months_not_180_days(self):
        last = datetime.date(2020, 1, 31)
        player = make_player(last_match_date=last)
        assert player.layoff_over_6_months(datetime.date(2020, 7, 30)) is False
        assert player.layoff_over_6_months(datetime.date(2020, 8, 1)) is True


class TestSurfaceElo:
    def test_debut_surface_uses_initial_elo_not_stored_value(self):
        player = make_player(
            surface_elos={"Hard": 1750.0, "Clay": 1650.0, "Grass": 1900.0},
            surface_match_counts={"Hard": 10, "Clay": 4, "Grass": 0},
        )
        assert player.surface_elo("Grass") == INITIAL_ELO
        assert player.surface_elo("Hard") == 1750.0

    def test_as_given_trusts_the_stored_debut_value(self, monkeypatch):
        monkeypatch.setattr(feature_builder, "SURFACE_DEBUT_ELO_MODE", "as_given")
        player = make_player(
            surface_elos={"Hard": 1750.0, "Clay": 1650.0, "Grass": 1900.0},
            surface_match_counts={"Hard": 10, "Clay": 4, "Grass": 0},
        )
        assert player.surface_elo("Grass") == 1900.0


class TestFromOrm:
    def test_reads_surface_attrs_and_recent_dates(self):
        player = SimpleNamespace(
            name="Alcaraz C.",
            elo_global=2100.0,
            elo_hard=2080.0,
            elo_clay=2000.0,
            elo_grass=1950.0,
            matches_hard=40,
            matches_clay=12,
            matches_grass=None,
            rank=1.0,
            last_match_date=datetime.date(2026, 8, 20),
            recent_matches=[
                SimpleNamespace(match_date=datetime.date(2026, 8, 18)),
                SimpleNamespace(match_date=datetime.date(2026, 8, 20)),
            ],
        )
        state = PlayerState.from_orm(player)
        assert state.name == "Alcaraz C."
        assert state.surface_elos["Hard"] == 2080.0
        assert state.surface_match_counts["Grass"] == 0
        assert state.recent_match_dates == [
            datetime.date(2026, 8, 18),
            datetime.date(2026, 8, 20),
        ]

    def test_nan_rank_becomes_none(self):
        state = make_player(rank=float("nan"))
        assert state.rank is None


class TestSwapOrientation:
    def test_negates_diffs_and_exchanges_layoff_flags(self):
        frame = pd.DataFrame(
            [
                {
                    "GlobalEloDiff": 100.0,
                    "SurfaceEloDiff": -20.0,
                    "RankDiff": 3.0,
                    "Player1LayoffOver6Months": 1.0,
                    "Player2LayoffOver6Months": 0.0,
                    "MatchesLast7DaysDiff": 2.0,
                }
            ],
            columns=MODEL_FEATURE_COLUMNS,
        )
        swapped = swap_orientation(frame)
        assert swapped.columns.tolist() == MODEL_FEATURE_COLUMNS
        for column in NEGATED_COLUMNS:
            assert swapped[column].iloc[0] == pytest.approx(-frame[column].iloc[0])
        first, second = SWAPPED_COLUMNS
        assert swapped[first].iloc[0] == frame[second].iloc[0]
        assert swapped[second].iloc[0] == frame[first].iloc[0]

    def test_applies_row_wise_to_a_multi_row_frame(self):
        frame = pd.DataFrame(
            [
                [10.0, 1.0, -1.0, 0.0, 1.0, 2.0],
                [-4.0, 8.0, 0.0, 1.0, 0.0, -3.0],
            ],
            columns=MODEL_FEATURE_COLUMNS,
        )
        swapped = swap_orientation(frame)
        assert swapped["GlobalEloDiff"].tolist() == [-10.0, 4.0]
        assert swapped["Player1LayoffOver6Months"].tolist() == [1.0, 0.0]
        assert swapped["Player2LayoffOver6Months"].tolist() == [0.0, 1.0]


class TestBuildFeatureFrame:
    def test_two_rows_second_is_the_swap_and_columns_match_contract(self):
        p1 = make_player(
            elo_global=2000.0,
            rank=2.0,
            last_match_date=datetime.date(2025, 1, 1),
            recent_match_dates=[datetime.date(2026, 8, 25)],
        )
        p2 = make_player(
            name="Other",
            elo_global=1800.0,
            rank=10.0,
            last_match_date=datetime.date(2026, 8, 1),
            recent_match_dates=[],
            surface_elos={"Hard": 1700.0, "Clay": 1650.0, "Grass": 1600.0},
            surface_match_counts={"Hard": 20, "Clay": 4, "Grass": 1},
        )
        frame = build_feature_frame(p1, p2, "Hard", PREDICTION_DATE)
        assert frame.columns.tolist() == MODEL_FEATURE_COLUMNS
        assert len(frame) == 2
        pd.testing.assert_frame_equal(
            frame.iloc[[1]].reset_index(drop=True),
            swap_orientation(frame.iloc[[0]]),
        )
        assert frame.iloc[0]["GlobalEloDiff"] == pytest.approx(200.0)
        assert frame.iloc[0]["MatchesLast7DaysDiff"] == pytest.approx(1.0)
        assert frame.iloc[0]["Player1LayoffOver6Months"] == pytest.approx(1.0)
        assert frame.iloc[0]["Player2LayoffOver6Months"] == pytest.approx(0.0)

    def test_swapping_players_reverses_the_two_rows(self):
        p1 = make_player(elo_global=2000.0, rank=1.0)
        p2 = make_player(
            name="Other",
            elo_global=1700.0,
            rank=20.0,
            last_match_date=datetime.date(2024, 1, 1),
        )
        forward = build_feature_frame(p1, p2, "Clay", PREDICTION_DATE)
        backward = build_feature_frame(p2, p1, "Clay", PREDICTION_DATE)
        pd.testing.assert_series_equal(
            forward.iloc[0], backward.iloc[1], check_names=False
        )
        pd.testing.assert_series_equal(
            forward.iloc[1], backward.iloc[0], check_names=False
        )

    def test_missing_rank_is_nan_in_the_frame(self):
        p1 = make_player(rank=None)
        p2 = make_player(name="Other", rank=4.0)
        frame = build_feature_frame(p1, p2, "Hard", PREDICTION_DATE)
        assert np.isnan(frame.iloc[0]["RankDiff"])
        assert np.isnan(frame.iloc[1]["RankDiff"])

    def test_debut_elo_affects_surface_diff(self):
        debut = make_player(
            elo_global=2000.0,
            surface_elos={"Hard": 2000.0, "Clay": 2000.0, "Grass": 2000.0},
            surface_match_counts={"Hard": 0, "Clay": 0, "Grass": 0},
        )
        veteran = make_player(
            name="Other",
            elo_global=2000.0,
            surface_elos={"Hard": 1800.0, "Clay": 1800.0, "Grass": 1800.0},
            surface_match_counts={"Hard": 30, "Clay": 10, "Grass": 5},
        )
        frame = build_feature_frame(debut, veteran, "Hard", PREDICTION_DATE)
        assert frame.iloc[0]["SurfaceEloDiff"] == pytest.approx(INITIAL_ELO - 1800.0)
