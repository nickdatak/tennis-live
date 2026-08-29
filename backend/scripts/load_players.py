"""Seed the players database from players.json (full wipe-and-reload).

Usage: python3 backend/scripts/load_players.py [--json PATH]

Works against DATABASE_URL from backend/.env (Supabase) or the dev SQLite
fallback when no .env is present. The daily updater will later replace this
one-shot seed.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATABASE_URL, PROJECT_ROOT
from app.db.database import SessionLocal, init_db
from app.db.models import Player, PlayerRecentMatch


def parse_date(value):
    if not value:
        return None
    return datetime.date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        type=Path,
        default=PROJECT_ROOT / "players.json",
        help="Path to the players JSON (default: project-root players.json)",
    )
    args = parser.parse_args()

    with open(args.json) as handle:
        raw_players = json.load(handle)
    assert isinstance(raw_players, dict) and raw_players, "Expected a dict of players."

    # This wipes and reloads the players table on a real Supabase database --
    # there is no local fallback to land on -- so say which one, loudly.
    print(f"Loading {len(raw_players):,} players from {args.json}")
    print(f"TARGET DATABASE: {DATABASE_URL.split('@')[-1]}")

    init_db()
    with SessionLocal() as session:
        deleted_matches = session.query(PlayerRecentMatch).delete()
        deleted_players = session.query(Player).delete()
        print(f"Cleared {deleted_players:,} players, {deleted_matches:,} recent-match rows")

        recent_total = 0
        for slug, entry in raw_players.items():
            elo = entry["elo"]
            matches = entry.get("matches", {})
            player = Player(
                slug=slug,
                name=entry["model_name"],
                rank=entry.get("rank"),
                elo_global=elo["overall"],
                elo_hard=elo["hard"],
                elo_clay=elo["clay"],
                elo_grass=elo["grass"],
                matches_global=int(matches.get("overall", 0)),
                matches_hard=int(matches.get("hard", 0)),
                matches_clay=int(matches.get("clay", 0)),
                matches_grass=int(matches.get("grass", 0)),
                last_match_date=parse_date(entry.get("last_match_date")),
                as_of=parse_date(entry.get("as_of")),
            )
            # Duplicate dates preserved: two matches in one day both count.
            for date_string in entry.get("recent_matches", []):
                player.recent_matches.append(
                    PlayerRecentMatch(match_date=parse_date(date_string))
                )
                recent_total += 1
            session.add(player)

        session.commit()
        print(f"Inserted {len(raw_players):,} players, {recent_total:,} recent-match rows")


if __name__ == "__main__":
    main()
