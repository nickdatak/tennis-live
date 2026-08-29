"""Prediction endpoint: look up both players, build features, run all six models."""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.database import get_session
from ..db.models import MatchResult
from ..schemas import HeadToHead, ModelPrediction, PredictRequest, PredictResponse
from ..services.feature_builder import PlayerState
from ..services.model_runner import model_runner
from .players import find_player, player_summary

router = APIRouter(prefix="/api/predict", tags=["predict"])


@router.post("", response_model=PredictResponse)
def predict(
    request: PredictRequest,
    session: Session = Depends(get_session),
) -> PredictResponse:
    if not model_runner.is_loaded:
        raise HTTPException(status_code=503, detail="Models are not loaded.")

    player1 = find_player(session, request.player1, include_recent_matches=True)
    player2 = find_player(session, request.player2, include_recent_matches=True)
    if player1.id == player2.id:
        raise HTTPException(
            status_code=400, detail="player1 and player2 must be different players."
        )

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
