"""SQLAlchemy ORM tables. Mirrored for Supabase in backend/app/db/schema.sql."""
from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Postgres gets BIGINT/BIGSERIAL as intended. SQLite must get plain INTEGER:
# only an `INTEGER PRIMARY KEY` column aliases SQLite's rowid, so a BIGINT
# primary key never auto-populates and every insert fails the NOT NULL check.
# That would break the dev fallback in backend/app/db/database.py, which is the
# whole point of the fallback existing.
BigId = BigInteger().with_variant(Integer, "sqlite")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, unique=True, index=True)  # research format, e.g. "Alcaraz C."
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

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    match_date: Mapped[datetime.date] = mapped_column(Date)

    player: Mapped[Player] = relationship(back_populates="recent_matches")


class MatchResult(Base):
    """Completed main-draw matches from the research snapshot. Feeds H2H display.

    Every row comes from research/data/output/matches_2015_onwards.csv — there is
    no other ingest, so the table needs no provenance column. Retired/walkover
    matches are never stored: the models were not trained on them, so they update
    nothing (by design)."""

    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    date: Mapped[datetime.date] = mapped_column(Date, index=True)
    surface: Mapped[str] = mapped_column(Text, nullable=True)
    tier: Mapped[str] = mapped_column(Text, nullable=True)
    tournament_name: Mapped[str] = mapped_column(Text, nullable=True)
    winner_id: Mapped[int] = mapped_column(BigId, ForeignKey("players.id"), index=True)
    loser_id: Mapped[int] = mapped_column(BigId, ForeignKey("players.id"), index=True)
    score: Mapped[str] = mapped_column(Text, nullable=True)


class BacktestRun(Base):
    """One backtest execution. Produced only by backend/scripts/run_backtest.py.

    The dashboard never computes a backtest — it reads these tables. Rerun
    locally when the models are replaced.
    """

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    dataset: Mapped[str] = mapped_column(Text)  # e.g. "test_2026"
    dataset_start: Mapped[datetime.date] = mapped_column(Date)
    dataset_end: Mapped[datetime.date] = mapped_column(Date)
    n_matches: Mapped[int] = mapped_column(Integer)
    # sha256 over the scored joblib files: lets a rerun detect unchanged models.
    models_fingerprint: Mapped[str] = mapped_column(Text)
    model_source: Mapped[str] = mapped_column(Text)
    trained_through: Mapped[datetime.date] = mapped_column(Date, nullable=True)
    stake: Mapped[float] = mapped_column(Float, default=1.0)

    results: Mapped[list["BacktestModelResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class BacktestModelResult(Base):
    """Aggregate scores for one model (or the Bet365 benchmark) in one run."""

    __tablename__ = "backtest_model_results"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(Text)
    is_benchmark: Mapped[bool] = mapped_column(Boolean, default=False)

    # Probability accuracy (models: all matches; Bet365: matches it priced).
    n_scored: Mapped[int] = mapped_column(Integer)
    brier: Mapped[float] = mapped_column(Float)
    log_loss: Mapped[float] = mapped_column(Float)
    accuracy: Mapped[float] = mapped_column(Float)

    # Flat-stake betting simulation against Bet365 prices.
    n_bets: Mapped[int] = mapped_column(Integer, default=0)
    n_bet_wins: Mapped[int] = mapped_column(Integer, default=0)
    staked: Mapped[float] = mapped_column(Float, default=0.0)
    profit: Mapped[float] = mapped_column(Float, default=0.0)
    roi: Mapped[float] = mapped_column(Float, nullable=True)

    run: Mapped[BacktestRun] = relationship(back_populates="results")


class BacktestMatch(Base):
    """One scored match, with the context recovered from the research dataset."""

    __tablename__ = "backtest_matches"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True
    )
    row_index: Mapped[int] = mapped_column(Integer)  # position in the split file
    match_date: Mapped[datetime.date] = mapped_column(Date, index=True)
    player1: Mapped[str] = mapped_column(Text)
    player2: Mapped[str] = mapped_column(Text)
    surface: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    series: Mapped[str] = mapped_column(Text, nullable=True)
    tournament: Mapped[str] = mapped_column(Text, nullable=True)
    player1_won: Mapped[bool] = mapped_column(Boolean)
    b365_p1_odds: Mapped[float] = mapped_column(Float, nullable=True)
    b365_p2_odds: Mapped[float] = mapped_column(Float, nullable=True)

    predictions: Mapped[list["BacktestPrediction"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class BacktestPrediction(Base):
    """One model's probability and resulting bet for one match."""

    __tablename__ = "backtest_predictions"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True
    )
    match_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("backtest_matches.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(Text, index=True)
    prob_player1: Mapped[float] = mapped_column(Float)
    # Betting outcome: bet_side is None when no positive-EV side existed.
    bet_side: Mapped[str] = mapped_column(Text, nullable=True)  # 'player1'|'player2'
    bet_odds: Mapped[float] = mapped_column(Float, nullable=True)
    bet_profit: Mapped[float] = mapped_column(Float, nullable=True)

    match: Mapped[BacktestMatch] = relationship(back_populates="predictions")
