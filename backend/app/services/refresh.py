"""Refresh player data from the Tennis API.

Flow (bounded by the request budget in tennis_api.py):
1. Window = day after the last processed date -> today.
2. Calendar -> main-tour tournaments possibly overlapping the window.
3. Per tournament: singles results; keep result_type == "completed" rows in
   the window that we haven't stored yet. Retired matches update nothing —
   the models were not trained on them (by design).
4. Elo updates replicating research/01_elo_calculation.ipynb exactly:
   date-grouped, start-of-day ratings, deltas applied at end of day, tier
   multipliers, surface-specific K.
5. Player stats: match counts, last_match_date, recent match dates.
6. Current rankings overwrite ranks for every matched player.

Everything is committed in one transaction at the end; any failure rolls the
whole run back.
"""
from __future__ import annotations

import datetime
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import (
    API_SURFACE_MAP,
    ELO_SCALE,
    GLOBAL_BASE_K,
    INITIAL_ELO,
    SURFACE_BASE_K,
    TIER_MULTIPLIERS,
)
from ..db.models import MatchResult, Player, PlayerRecentMatch, RefreshLog
from .name_matching import AMBIGUOUS, RESOLVED, UNKNOWN, resolve_api_player
from .tennis_api import TennisApiClient

# A tournament starting this many days before the window can still have
# matches inside it (two-week draws + finals spillover).
TOURNAMENT_LOOKBACK_DAYS = 21
RECENT_MATCH_RETENTION_DAYS = 60

_refresh_lock = threading.Lock()


class RefreshInProgress(RuntimeError):
    pass


def _window_start(session: Session) -> datetime.date:
    """Day after the last processed date (refresh watermark or seed as_of)."""
    last_refresh = session.scalar(
        select(func.max(RefreshLog.window_end)).where(RefreshLog.status == "ok")
    )
    seed_as_of = session.scalar(select(func.max(Player.as_of)))
    anchors = [d for d in (last_refresh, seed_as_of) if d is not None]
    if not anchors:
        raise RuntimeError("No players seeded; run load_players.py first.")
    return max(anchors) + datetime.timedelta(days=1)


def _parse_match_date(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value[:10])


def _slug_for(session: Session, full_name: str) -> str:
    base = "".join(c if c.isalnum() else "_" for c in full_name.lower()).strip("_")
    slug = base or "player"
    counter = 2
    while session.scalars(select(Player).where(Player.slug == slug)).first():
        slug = f"{base}_{counter}"
        counter += 1
    return slug


def _get_or_create_player(
    session: Session,
    api_player_id: int,
    full_name: str,
    created: Dict[int, Player],
    warnings: List[str],
) -> Optional[Player]:
    if api_player_id in created:
        return created[api_player_id]
    player, status = resolve_api_player(session, api_player_id, full_name)
    if status == RESOLVED:
        return player
    if status == AMBIGUOUS:
        warnings.append(f"Ambiguous name mapping for {full_name!r}; match skipped.")
        return None
    # UNKNOWN -> brand-new player at the research initial state.
    player = Player(
        slug=_slug_for(session, full_name),
        name=full_name,  # full API name; research-style rename can happen later
        api_player_id=api_player_id,
        rank=None,
        elo_global=INITIAL_ELO,
        elo_hard=INITIAL_ELO,
        elo_clay=INITIAL_ELO,
        elo_grass=INITIAL_ELO,
        matches_global=0,
        matches_hard=0,
        matches_clay=0,
        matches_grass=0,
        last_match_date=None,
    )
    session.add(player)
    session.flush()
    created[api_player_id] = player
    return player


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / ELO_SCALE))


SURFACE_ELO_ATTR = {"Hard": "elo_hard", "Clay": "elo_clay", "Grass": "elo_grass"}
SURFACE_COUNT_ATTR = {"Hard": "matches_hard", "Clay": "matches_clay", "Grass": "matches_grass"}


def _apply_elo_updates(
    matches: List[dict], players: Dict[int, Player]
) -> None:
    """Research-identical Elo: per date, pre-values from start-of-day state."""
    by_date: Dict[datetime.date, List[dict]] = defaultdict(list)
    for match in matches:
        by_date[match["date"]].append(match)

    for match_date in sorted(by_date):
        global_deltas: Dict[int, float] = defaultdict(float)
        surface_deltas: Dict[Tuple[int, str], float] = defaultdict(float)

        for match in by_date[match_date]:
            winner = players[match["winner_db_id"]]
            loser = players[match["loser_db_id"]]
            multiplier = TIER_MULTIPLIERS[match["tier"]]

            win_probability = _expected_score(winner.elo_global, loser.elo_global)
            assert 0.0 < win_probability < 1.0
            change = GLOBAL_BASE_K * multiplier * (1.0 - win_probability)
            global_deltas[winner.id] += change
            global_deltas[loser.id] -= change

            surface = match["surface"]
            if surface in SURFACE_BASE_K:
                elo_attr = SURFACE_ELO_ATTR[surface]
                surface_probability = _expected_score(
                    getattr(winner, elo_attr), getattr(loser, elo_attr)
                )
                surface_change = (
                    SURFACE_BASE_K[surface] * multiplier * (1.0 - surface_probability)
                )
                surface_deltas[(winner.id, surface)] += surface_change
                surface_deltas[(loser.id, surface)] -= surface_change

        # End of day: apply accumulated deltas (start-of-day batching).
        by_id = {p.id: p for p in players.values()}
        for player_id, delta in global_deltas.items():
            by_id[player_id].elo_global += delta
        for (player_id, surface), delta in surface_deltas.items():
            attr = SURFACE_ELO_ATTR[surface]
            setattr(by_id[player_id], attr, getattr(by_id[player_id], attr) + delta)


def run_refresh(session: Session) -> dict:
    if not _refresh_lock.acquire(blocking=False):
        raise RefreshInProgress("A refresh is already running.")
    client = TennisApiClient()
    try:
        return _run_refresh_inner(session, client)
    except Exception as error:
        session.rollback()
        session.add(
            RefreshLog(
                window_start=datetime.date.today(),
                window_end=datetime.date.today(),
                status="error",
                requests_used=client.requests_used,
                detail=f"{type(error).__name__}: {error}"[:500],
            )
        )
        session.commit()
        raise
    finally:
        client.close()
        _refresh_lock.release()


def _run_refresh_inner(session: Session, client: TennisApiClient) -> dict:
    window_start = _window_start(session)
    window_end = datetime.date.today()
    if window_start > window_end:
        return {
            "status": "ok",
            "detail": "Already up to date.",
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "matches_applied": 0,
            "retired_skipped": 0,
            "new_players": 0,
            "rank_updates": 0,
            "requests_used": 0,
            "warnings": [],
        }

    # Tournaments that can contain window matches.
    lookback = window_start - datetime.timedelta(days=TOURNAMENT_LOOKBACK_DAYS)
    years = sorted({lookback.year, window_end.year})
    tournaments = []
    for year in years:
        tournaments.extend(client.calendar_main_tour(year, since=lookback))
    tournaments = [
        t for t in tournaments if _parse_match_date(t["date"]) <= window_end
    ]

    known_match_ids = {
        row for row in session.scalars(select(MatchResult.api_match_id)) if row
    }

    warnings: List[str] = []
    created: Dict[int, Player] = {}
    matches: List[dict] = []
    retired_skipped = 0

    for tournament in tournaments:
        surface = API_SURFACE_MAP.get((tournament.get("court") or {}).get("name"))
        tier = tournament["tier"]
        for row in client.tournament_singles_results(tournament["id"]):
            api_match_id = str(row.get("id", ""))
            result_type = (row.get("result_type") or "").lower()
            if not row.get("date") or not api_match_id:
                continue
            match_date = _parse_match_date(row["date"])
            if not (window_start <= match_date <= window_end):
                continue
            if api_match_id in known_match_ids:
                continue
            if result_type != "completed":
                retired_skipped += 1  # retired/walkover: models weren't trained on these
                continue

            winner_api_id = row.get("match_winner")
            player1, player2 = row.get("player1") or {}, row.get("player2") or {}
            if winner_api_id == player1.get("id"):
                winner_api, loser_api = player1, player2
            elif winner_api_id == player2.get("id"):
                winner_api, loser_api = player2, player1
            else:
                warnings.append(f"Match {api_match_id}: winner id mismatch; skipped.")
                continue

            winner = _get_or_create_player(
                session, winner_api["id"], winner_api.get("name", ""), created, warnings
            )
            loser = _get_or_create_player(
                session, loser_api["id"], loser_api.get("name", ""), created, warnings
            )
            if winner is None or loser is None:
                continue

            matches.append(
                {
                    "api_match_id": api_match_id,
                    "date": match_date,
                    "surface": surface,
                    "tier": tier,
                    "tournament_name": tournament.get("name"),
                    "winner_db_id": winner.id,
                    "loser_db_id": loser.id,
                    "score": row.get("result"),
                }
            )

    players: Dict[int, Player] = {}
    for match in matches:
        for key in ("winner_db_id", "loser_db_id"):
            if match[key] not in players:
                players[match[key]] = session.get(Player, match[key])

    _apply_elo_updates(matches, players)

    # Stats, history, and stored results.
    retention_cutoff = window_end - datetime.timedelta(days=RECENT_MATCH_RETENTION_DAYS)
    for match in sorted(matches, key=lambda m: m["date"]):
        winner = players[match["winner_db_id"]]
        loser = players[match["loser_db_id"]]
        for player in (winner, loser):
            player.matches_global += 1
            if match["surface"] in SURFACE_COUNT_ATTR:
                attr = SURFACE_COUNT_ATTR[match["surface"]]
                setattr(player, attr, getattr(player, attr) + 1)
            if player.last_match_date is None or match["date"] > player.last_match_date:
                player.last_match_date = match["date"]
            if match["date"] >= retention_cutoff:
                session.add(
                    PlayerRecentMatch(player_id=player.id, match_date=match["date"])
                )
        session.add(
            MatchResult(
                api_match_id=match["api_match_id"],
                source="api",
                date=match["date"],
                surface=match["surface"],
                tier=match["tier"],
                tournament_name=match["tournament_name"],
                winner_id=winner.id,
                loser_id=loser.id,
                score=match["score"],
            )
        )
    for player in players.values():
        player.as_of = window_end

    # Prune stale recent-match rows.
    session.query(PlayerRecentMatch).filter(
        PlayerRecentMatch.match_date < retention_cutoff
    ).delete(synchronize_session=False)

    # Rankings: current snapshot overwrites ranks for matched players.
    rank_updates = 0
    for entry in client.rankings_singles():
        api_player = entry.get("player") or {}
        api_id, position = api_player.get("id"), entry.get("position")
        if api_id is None or position is None:
            continue
        player, status = resolve_api_player(session, api_id, api_player.get("name", ""))
        if status == RESOLVED and player is not None:
            if player.rank != float(position):
                player.rank = float(position)
                rank_updates += 1

    log = RefreshLog(
        window_start=window_start,
        window_end=window_end,
        status="ok",
        matches_applied=len(matches),
        retired_skipped=retired_skipped,
        new_players=len(created),
        rank_updates=rank_updates,
        requests_used=client.requests_used,
        detail="; ".join(warnings)[:500] if warnings else None,
    )
    session.add(log)
    session.commit()

    return {
        "status": "ok",
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "matches_applied": len(matches),
        "retired_skipped": retired_skipped,
        "new_players": len(created),
        "rank_updates": rank_updates,
        "requests_used": client.requests_used,
        "warnings": warnings,
    }
