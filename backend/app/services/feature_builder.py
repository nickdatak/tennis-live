"""Build the six-feature model input, mirroring the research pipeline exactly.

Training semantics reproduced here (see research/02_feature_creation.ipynb):
- MatchesLast7Days: completed matches on dates d with
  prediction_date - 7 days <= d < prediction_date (the boundary date counts,
  the prediction day itself never does; same-day duplicates each count).
- LayoffOver6Months: prediction_date > last_match_date + 6 calendar months;
  unknown when the player has no prior match (NaN -> pipeline imputer).
- Surface Elo: a player who never played the surface starts at 1500
  ("initial" mode, training-faithful) unless configured to trust the stored
  value ("as_given").
"""
from __future__ import annotations

import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

from ..config import (
    INITIAL_ELO,
    MODEL_FEATURE_COLUMNS,
    SURFACE_DEBUT_ELO_MODE,
    SURFACES,
)

WORKLOAD_WINDOW_DAYS = 7
LAYOFF_MONTHS = 6

_SURFACE_ATTRS = {
    "Hard": ("elo_hard", "matches_hard"),
    "Clay": ("elo_clay", "matches_clay"),
    "Grass": ("elo_grass", "matches_grass"),
}


class PlayerState:
    """Snapshot of one player's pre-match state, as read from the database."""

    def __init__(
        self,
        name: str,
        elo_global: float,
        surface_elos: dict,
        surface_match_counts: dict,
        rank: Optional[float],
        last_match_date: Optional[datetime.date],
        recent_match_dates: List[datetime.date],
    ):
        self.name = name
        self.elo_global = float(elo_global)
        self.surface_elos = surface_elos
        self.surface_match_counts = surface_match_counts
        self.rank = None if rank is None or pd.isna(rank) else float(rank)
        self.last_match_date = last_match_date
        self.recent_match_dates = recent_match_dates

    @classmethod
    def from_orm(cls, player) -> "PlayerState":
        return cls(
            name=player.name,
            elo_global=player.elo_global,
            surface_elos={
                surface: getattr(player, elo_attr)
                for surface, (elo_attr, _) in _SURFACE_ATTRS.items()
            },
            surface_match_counts={
                surface: getattr(player, count_attr) or 0
                for surface, (_, count_attr) in _SURFACE_ATTRS.items()
            },
            rank=player.rank,
            last_match_date=player.last_match_date,
            recent_match_dates=[rm.match_date for rm in player.recent_matches],
        )

    def surface_elo(self, surface: str) -> float:
        assert surface in SURFACES
        if (
            SURFACE_DEBUT_ELO_MODE == "initial"
            and self.surface_match_counts.get(surface, 0) == 0
        ):
            return INITIAL_ELO
        return float(self.surface_elos[surface])

    def matches_last_7_days(self, prediction_date: datetime.date) -> int:
        cutoff = prediction_date - datetime.timedelta(days=WORKLOAD_WINDOW_DAYS)
        return sum(1 for d in self.recent_match_dates if cutoff <= d < prediction_date)

    def layoff_over_6_months(self, prediction_date: datetime.date) -> Optional[bool]:
        if self.last_match_date is None:
            return None
        threshold = (
            pd.Timestamp(self.last_match_date) + pd.DateOffset(months=LAYOFF_MONTHS)
        ).date()
        return prediction_date > threshold


def _layoff_to_float(value: Optional[bool]) -> float:
    if value is None:
        return np.nan
    return 1.0 if value else 0.0


def _rank_diff(rank1: Optional[float], rank2: Optional[float]) -> float:
    if rank1 is None or rank2 is None:
        return np.nan
    return rank1 - rank2


def build_feature_frame(
    player1: PlayerState,
    player2: PlayerState,
    surface: str,
    prediction_date: datetime.date,
) -> pd.DataFrame:
    """Two rows: player1-first orientation, then the swapped orientation.

    Predictions from both are averaged so that the result does not depend on
    input order (training randomized orientation, so neither is canonical).
    """
    p1_workload = player1.matches_last_7_days(prediction_date)
    p2_workload = player2.matches_last_7_days(prediction_date)
    p1_layoff = _layoff_to_float(player1.layoff_over_6_months(prediction_date))
    p2_layoff = _layoff_to_float(player2.layoff_over_6_months(prediction_date))

    global_diff = player1.elo_global - player2.elo_global
    surface_diff = player1.surface_elo(surface) - player2.surface_elo(surface)
    rank_diff = _rank_diff(player1.rank, player2.rank)
    workload_diff = float(p1_workload - p2_workload)

    rows = [
        {
            "GlobalEloDiff": global_diff,
            "SurfaceEloDiff": surface_diff,
            "RankDiff": rank_diff,
            "Player1LayoffOver6Months": p1_layoff,
            "Player2LayoffOver6Months": p2_layoff,
            "MatchesLast7DaysDiff": workload_diff,
        },
        {
            "GlobalEloDiff": -global_diff,
            "SurfaceEloDiff": -surface_diff,
            "RankDiff": -rank_diff if not np.isnan(rank_diff) else np.nan,
            "Player1LayoffOver6Months": p2_layoff,
            "Player2LayoffOver6Months": p1_layoff,
            "MatchesLast7DaysDiff": -workload_diff,
        },
    ]
    frame = pd.DataFrame(rows, columns=MODEL_FEATURE_COLUMNS, dtype=float)
    assert frame.columns.tolist() == MODEL_FEATURE_COLUMNS
    return frame
