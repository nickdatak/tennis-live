"""Player lookup / autocomplete endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db.database import get_session
from ..db.models import Player
from ..schemas import (
    PlayerComparisonResponse,
    PlayerProfile,
    PlayerSearchResponse,
    PlayerSummary,
)

router = APIRouter(prefix="/api/players", tags=["players"])


def find_player(
    session: Session,
    identifier: str,
    *,
    include_recent_matches: bool = False,
) -> Player:
    """Find one player by exact name or slug, case-insensitively."""
    lowered = identifier.strip().lower()
    statement = select(Player).where(
        (func.lower(Player.name) == lowered)
        | (func.lower(Player.slug) == lowered)
    )
    if include_recent_matches:
        statement = statement.options(selectinload(Player.recent_matches))

    player = session.scalars(statement).first()
    if player is None:
        raise HTTPException(
            status_code=404,
            detail=f"Player not found in database: {identifier!r}. "
            "Use /api/players?q= to search for the exact name.",
        )
    return player


def player_summary(player: Player) -> PlayerSummary:
    return PlayerSummary(
        slug=player.slug,
        name=player.name,
        rank=player.rank,
        elo_global=player.elo_global,
        last_match_date=player.last_match_date,
    )


def player_profile(player: Player, surface: str) -> PlayerProfile:
    """Build a compact database profile for the selected match surface."""
    surface_key = surface.lower()
    return PlayerProfile(
        slug=player.slug,
        name=player.name,
        rank=player.rank,
        elo_global=player.elo_global,
        elo_surface=getattr(player, f"elo_{surface_key}"),
        matches_global=player.matches_global,
        matches_surface=getattr(player, f"matches_{surface_key}"),
        last_match_date=player.last_match_date,
        as_of=player.as_of,
    )


@router.get("/all", response_model=PlayerSearchResponse)
def all_players(session: Session = Depends(get_session)) -> PlayerSearchResponse:
    """Full player list (~900 rows, ~70KB) for client-side autocomplete caching."""
    players = session.scalars(
        select(Player).order_by(
            Player.rank.is_(None), Player.rank.asc(), Player.name.asc()
        )
    ).all()
    return PlayerSearchResponse(query="", players=[player_summary(p) for p in players])


@router.get("/compare", response_model=PlayerComparisonResponse)
def compare_players(
    player1: str = Query(..., min_length=1, max_length=100),
    player2: str = Query(..., min_length=1, max_length=100),
    surface: Literal["Hard", "Clay", "Grass"] = Query(...),
    session: Session = Depends(get_session),
) -> PlayerComparisonResponse:
    """Return both database profiles needed by the prediction results view."""
    first = find_player(session, player1)
    second = find_player(session, player2)
    if first.id == second.id:
        raise HTTPException(
            status_code=400, detail="player1 and player2 must be different players."
        )
    return PlayerComparisonResponse(
        player1=player_profile(first, surface),
        player2=player_profile(second, surface),
        surface=surface,
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
