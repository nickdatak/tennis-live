"""Pydantic request/response contracts for the API."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

try:  # Literal lives in typing from 3.8+, keep explicit for clarity
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal


class PlayerSummary(BaseModel):
    slug: str
    name: str
    rank: Optional[float] = None
    elo_global: float
    last_match_date: Optional[datetime.date] = None


class PlayerProfile(PlayerSummary):
    elo_surface: float
    matches_global: int
    matches_surface: int
    as_of: Optional[datetime.date] = None


class PlayerSearchResponse(BaseModel):
    query: str
    players: List[PlayerSummary]


class PlayerComparisonResponse(BaseModel):
    player1: PlayerProfile
    player2: PlayerProfile
    surface: Literal["Hard", "Clay", "Grass"]


class PredictRequest(BaseModel):
    player1: str = Field(min_length=1)
    player2: str = Field(min_length=1)
    surface: Literal["Hard", "Clay", "Grass"]


class ModelPrediction(BaseModel):
    model: str
    player1_win_probability: float


class HeadToHead(BaseModel):
    player1_wins: int
    player2_wins: int
    since: Optional[datetime.date] = None  # earliest stored match, if any


class PredictResponse(BaseModel):
    player1: PlayerSummary
    player2: PlayerSummary
    surface: str
    prediction_date: datetime.date
    predictions: List[ModelPrediction]
    mean_player1_win_probability: float
    features_player1_first: Dict[str, Optional[float]]
    head_to_head: HeadToHead


class BacktestModelScore(BaseModel):
    model: str
    is_benchmark: bool
    n_scored: int
    brier: float
    log_loss: float
    accuracy: float
    n_bets: int
    n_bet_wins: int
    staked: float
    profit: float
    roi: Optional[float] = None


class BacktestSummary(BaseModel):
    run_id: int
    computed_at: Optional[datetime.datetime] = None
    dataset: str
    dataset_start: datetime.date
    dataset_end: datetime.date
    n_matches: int
    trained_through: Optional[datetime.date] = None
    model_source: str
    stake: float
    models: List[BacktestModelScore]


class EquityPoint(BaseModel):
    date: datetime.date
    cumulative_profit: float
    cumulative_bets: int
    roi: float  # running return on stake so far, comparable across models


class EquitySeries(BaseModel):
    model: str
    n_bets: int
    n_wins: int
    profit: float
    roi: Optional[float] = None
    points: List[EquityPoint]


class EquityResponse(BaseModel):
    run_id: int
    surface: str  # "All" or a single surface
    stake: float
    series: List[EquitySeries]


class HealthResponse(BaseModel):
    status: str
    models_loaded: int
    database: str
    using_dev_sqlite: bool
    players_in_db: Optional[int] = None
    startup_errors: List[str] = []
