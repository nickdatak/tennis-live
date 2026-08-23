"""Player lookup / autocomplete endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.database import get_session
from ..db.models import Player
from ..schemas import PlayerSearchResponse, PlayerSummary

router = APIRouter(prefix="/api/players", tags=["players"])


def player_summary(player: Player) -> PlayerSummary:
    return PlayerSummary(
        slug=player.slug,
        name=player.name,
        rank=player.rank,
        elo_global=player.elo_global,
        last_match_date=player.last_match_date,
    )


@router.get("", response_model=PlayerSearchResponse)
def search_players(
    q: str = Query("", max_length=100),
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> PlayerSearchResponse:
    """Case-insensitive substring search over player names; ranked players first."""
    query = q.strip()
    statement = select(Player)
    if query:
        pattern = f"%{query.lower()}%"
        statement = statement.where(
            func.lower(Player.name).like(pattern)
            | func.lower(Player.slug).like(pattern)
        )
    statement = statement.order_by(
        Player.rank.is_(None), Player.rank.asc(), Player.name.asc()
    ).limit(limit)
    players = session.scalars(statement).all()
    return PlayerSearchResponse(
        query=query, players=[player_summary(p) for p in players]
    )
