"""SQLAlchemy ORM tables. Mirrored for Supabase in backend/app/db/schema.sql."""
from __future__ import annotations

import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)  # research format, e.g. "Alcaraz C."
    api_player_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=True, index=True)
    rank: Mapped[float] = mapped_column(Float, nullable=True)
    elo_global: Mapped[float] = mapped_column(Float)
    elo_hard: Mapped[float] = mapped_column(Float)
    elo_clay: Mapped[float] = mapped_column(Float)
    elo_grass: Mapped[float] = mapped_column(Float)
    matches_global: Mapped[int] = mapped_column(Integer, default=0)
    matches_hard: Mapped[int] = mapped_column(Integer, default=0)
    matches_clay: Mapped[int] = mapped_column(Integer, default=0)
    matches_grass: Mapped[int] = mapped_column(Integer, default=0)
    last_match_date: Mapped[datetime.date] = mapped_column(Date, nullable=True)
    as_of: Mapped[datetime.date] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    recent_matches: Mapped[list["PlayerRecentMatch"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )


class PlayerRecentMatch(Base):
    """One row per match; duplicates on the same date are meaningful
    (two matches in a day both count toward the 7-day workload)."""

    __tablename__ = "player_recent_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    match_date: Mapped[datetime.date] = mapped_column(Date)

    player: Mapped[Player] = relationship(back_populates="recent_matches")


class MatchResult(Base):
    """Completed main-draw matches. Feeds H2H display and dedupes refreshes.

    Retired/walkover matches are never stored: the models were not trained on
    them, so they update nothing (by design)."""

    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_match_id: Mapped[str] = mapped_column(String, unique=True, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String, default="api")  # 'api' | 'research'
    date: Mapped[datetime.date] = mapped_column(Date, index=True)
    surface: Mapped[str] = mapped_column(String, nullable=True)
    tier: Mapped[str] = mapped_column(String, nullable=True)
    tournament_name: Mapped[str] = mapped_column(String, nullable=True)
    winner_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    loser_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    score: Mapped[str] = mapped_column(String, nullable=True)


class RefreshLog(Base):
    """One row per refresh run; the latest successful row is the watermark."""

    __tablename__ = "refresh_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ran_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    window_start: Mapped[datetime.date] = mapped_column(Date)
    window_end: Mapped[datetime.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String)  # 'ok' | 'error'
    matches_applied: Mapped[int] = mapped_column(Integer, default=0)
    retired_skipped: Mapped[int] = mapped_column(Integer, default=0)
    new_players: Mapped[int] = mapped_column(Integer, default=0)
    rank_updates: Mapped[int] = mapped_column(Integer, default=0)
    requests_used: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String, nullable=True)
