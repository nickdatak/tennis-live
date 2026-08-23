"""Resolve Tennis API players (full names + stable IDs) to database players.

The database uses research/tennis-data naming ("Alcaraz C.", "Struff J.L.",
"Auger-Aliassime F.", "Vallejo D." for Adolfo Daniel Vallejo), while the API
sends full names ("Jan-Lennard Struff"). Resolution order:

1. `players.api_player_id` — authoritative once stored.
2. Candidate research-style names generated from the full name (surname spans
   x initial variants), compared after stripping dots/spaces/hyphens/case.
   When several DB name variants hit (the seed contains duplicate identities
   like "Tirante T.A." / "Tirante T. A."), the player with the most recorded
   matches wins — that is the canonical identity. The api id is stored so
   step 1 wins next time.
3. No hit -> the caller creates a new player (Elo 1500, research-default).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Player

RESOLVED = "resolved"
UNKNOWN = "unknown"  # safe to create a new player
AMBIGUOUS = "ambiguous"  # do NOT create; skip and report


def normalize(name: str) -> str:
    """Comparison form: letters only, lowercase ("Struff J.L." -> "struffjl")."""
    return re.sub(r"[^a-z]", "", name.lower())


def candidate_research_names(full_name: str) -> List[str]:
    """Research-style candidates for an API full name, most specific first.

    "Jan-Lennard Struff" -> ["Struff J.L.", "Struff J.", "Struff L."];
    "Adolfo Daniel Vallejo" -> includes "Vallejo A.D.", "Vallejo A.",
    "Vallejo D."; "Pedro Martinez Portero" -> "Martinez Portero P.",
    "Martinez P.", "Portero P.", ...
    """
    tokens = [t for t in re.split(r"[\s-]+", full_name.strip()) if t]
    if len(tokens) < 2:
        return []

    candidates: List[str] = []

    def add(candidate: str) -> None:
        if candidate not in candidates:
            candidates.append(candidate)

    for split in range(1, len(tokens)):
        given, surnames = tokens[:split], tokens[split:]
        initial_variants = ["".join(f"{g[0].upper()}." for g in given)]
        for g in given:
            initial_variants.append(f"{g[0].upper()}.")
        surname_spans = []
        n = len(surnames)
        for length in range(n, 0, -1):
            for start in range(0, n - length + 1):
                surname_spans.append(" ".join(surnames[start : start + length]))
        for span in surname_spans:
            for initials in initial_variants:
                add(f"{span} {initials}")
    return candidates


def resolve_api_player(
    session: Session, api_player_id: int, full_name: str
) -> Tuple[Optional[Player], str]:
    """Find the DB player for an API player, storing the mapping on success."""
    player = session.scalars(
        select(Player).where(Player.api_player_id == api_player_id)
    ).first()
    if player is not None:
        return player, RESOLVED

    candidates = candidate_research_names(full_name)
    if not candidates:
        return None, UNKNOWN
    by_priority = {normalize(c): i for i, c in reversed(list(enumerate(candidates)))}

    hits = []
    for db_player in session.scalars(select(Player)).all():
        priority = by_priority.get(normalize(db_player.name))
        if priority is not None:
            hits.append((priority, db_player))
    # Only identities not already claimed by a different api id are eligible.
    hits = [
        (priority, p)
        for priority, p in hits
        if p.api_player_id is None or p.api_player_id == api_player_id
    ]
    if not hits:
        return None, UNKNOWN

    # Canonical identity: the one with the most recorded matches; candidate
    # specificity breaks ties. A dead heat is genuine ambiguity.
    hits.sort(key=lambda item: (-(item[1].matches_global or 0), item[0]))
    if (
        len(hits) > 1
        and (hits[0][1].matches_global or 0) == (hits[1][1].matches_global or 0)
        and hits[0][0] == hits[1][0]
    ):
        return None, AMBIGUOUS
    player = hits[0][1]
    player.api_player_id = api_player_id
    return player, RESOLVED
