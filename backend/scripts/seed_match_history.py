"""Backfill match_results from the research dataset (read-only) for H2H display.

Usage: python3 backend/scripts/seed_match_history.py

Reads research/data/output/matches_2015_onwards.csv (never writes to
research/), keeps completed matches whose players exist in the players table,
and stores them with source='research'. Elo/stats are NOT touched — the seed
players.json already reflects this history. Idempotent: wipes and reloads only
the source='research' rows.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from sqlalchemy import select

from app.config import PROJECT_ROOT
from app.db.database import SessionLocal, init_db
from app.db.models import MatchResult, Player

CSV_PATH = PROJECT_ROOT / "research" / "data" / "output" / "matches_2015_onwards.csv"


def build_score(row: pd.Series) -> str:
    sets = []
    for i in range(1, 6):
        w, l = row.get(f"W{i}"), row.get(f"L{i}")
        if pd.notna(w) and pd.notna(l):
            try:
                sets.append(f"{int(float(w))}-{int(float(l))}")
            except (TypeError, ValueError):
                continue
    return " ".join(sets)


def main() -> None:
    frame = pd.read_csv(CSV_PATH, parse_dates=["Date"], low_memory=False)
    completed = frame.loc[frame["Comment"].eq("Completed")].copy()
    print(f"Read {len(frame):,} rows; {len(completed):,} completed (read-only source)")

    init_db()
    with SessionLocal() as session:
        players_by_name = {
            p.name: p.id for p in session.scalars(select(Player)).all()
        }
        deleted = (
            session.query(MatchResult)
            .filter(MatchResult.source == "research")
            .delete(synchronize_session=False)
        )
        print(f"Cleared {deleted:,} existing research-sourced rows")

        inserted = skipped = 0
        for row in completed.itertuples(index=False):
            winner_id = players_by_name.get(row.Winner)
            loser_id = players_by_name.get(row.Loser)
            if winner_id is None or loser_id is None:
                skipped += 1
                continue
            session.add(
                MatchResult(
                    api_match_id=None,
                    source="research",
                    date=row.Date.date(),
                    surface=row.Surface if pd.notna(row.Surface) else None,
                    tier=row.Series if pd.notna(row.Series) else None,
                    tournament_name=row.Tournament if pd.notna(row.Tournament) else None,
                    winner_id=winner_id,
                    loser_id=loser_id,
                    score=build_score(pd.Series(row._asdict())),
                )
            )
            inserted += 1
        session.commit()
        print(f"Inserted {inserted:,} matches ({skipped:,} skipped: player not in seed)")


if __name__ == "__main__":
    main()
