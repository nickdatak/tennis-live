"""Prediction endpoint: look up both players, build features, run all six models."""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db.database import get_session
from ..db.models import MatchResult, Player
from ..schemas import HeadToHead, ModelPrediction, PredictRequest, PredictResponse
from ..services.feature_builder import PlayerState
from ..services.model_runner import model_runner
from .players import player_summary

router = APIRouter(prefix="/api/predict", tags=["predict"])


def _find_player(session: Session, identifier: str) -> Player:
    """Exact match on name or slug, case-insensitive."""
    lowered = identifier.strip().lower()
    statement = (
        select(Player)
        .where(
            (func.lower(Player.name) == lowered)
            | (func.lower(Player.slug) == lowered)
        )
        .options(selectinload(Player.recent_matches))
    )
    player = session.scalars(statement).first()
    if player is None:
        raise HTTPException(
            status_code=404,
            detail=f"Player not found in database: {identifier!r}. "
            "Use /api/players?q= to search for the exact name.",
        )
    return player


@router.post("", response_model=PredictResponse)
def predict(
    request: PredictRequest,
    session: Session = Depends(get_session),
) -> PredictResponse:
    if not model_runner.is_loaded:
        raise HTTPException(status_code=503, detail="Models are not loaded.")

    player1 = _find_player(session, request.player1)
    player2 = _find_player(session, request.player2)
    if player1.id == player2.id:
        raise HTTPException(
            status_code=400, detail="player1 and player2 must be different players."
        )

    # H2H is display-only: completed matches stored in match_results.
    # It is never a model input (the six-feature contract has no H2H).
    pair_matches = session.scalars(
        select(MatchResult).where(
            ((MatchResult.winner_id == player1.id) & (MatchResult.loser_id == player2.id))
            | ((MatchResult.winner_id == player2.id) & (MatchResult.loser_id == player1.id))
        )
    ).all()
    head_to_head = HeadToHead(
        player1_wins=sum(1 for m in pair_matches if m.winner_id == player1.id),
        player2_wins=sum(1 for m in pair_matches if m.winner_id == player2.id),
        since=min((m.date for m in pair_matches), default=None),
    )

    prediction_date = datetime.date.today()
    result = model_runner.predict(
        PlayerState.from_orm(player1),
        PlayerState.from_orm(player2),
        request.surface,
        prediction_date,
    )

    return PredictResponse(
        player1=player_summary(player1),
        player2=player_summary(player2),
        surface=request.surface,
        prediction_date=prediction_date,
        predictions=[
            ModelPrediction(model=name, player1_win_probability=probability)
            for name, probability in result["per_model"].items()
        ],
        mean_player1_win_probability=result["mean"],
        features_player1_first=result["features_player1_first"],
        head_to_head=head_to_head,
    )
