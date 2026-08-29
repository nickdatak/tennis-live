"""In-memory row helpers for API tests."""
from __future__ import annotations

import datetime

from app.db.models import (
    BacktestMatch,
    BacktestModelResult,
    BacktestPrediction,
    BacktestRun,
    MatchResult,
    Player,
    PlayerRecentMatch,
)


def add_player(
    session,
    *,
    id: int,
    slug: str,
    name: str,
    rank=None,
    elo_global: float = 1800.0,
    elo_hard: float = 1800.0,
    elo_clay: float = 1700.0,
    elo_grass: float = 1600.0,
    matches_global: int = 10,
    matches_hard: int = 8,
    matches_clay: int = 2,
    matches_grass: int = 0,
    last_match_date=None,
    as_of=None,
    recent_dates=None,
) -> Player:
    player = Player(
        id=id,
        slug=slug,
        name=name,
        rank=rank,
        elo_global=elo_global,
        elo_hard=elo_hard,
        elo_clay=elo_clay,
        elo_grass=elo_grass,
        matches_global=matches_global,
        matches_hard=matches_hard,
        matches_clay=matches_clay,
        matches_grass=matches_grass,
        last_match_date=last_match_date,
        as_of=as_of,
    )
    # BigInteger PKs do not autoincrement on SQLite; assign ids explicitly.
    for index, match_date in enumerate(recent_dates or [], start=1):
        player.recent_matches.append(
            PlayerRecentMatch(id=id * 100 + index, match_date=match_date)
        )
    session.add(player)
    session.commit()
    return player


def add_match_result(
    session,
    *,
    id: int,
    winner_id: int,
    loser_id: int,
    date: datetime.date,
    surface: str = "Hard",
) -> MatchResult:
    row = MatchResult(
        id=id,
        date=date,
        surface=surface,
        winner_id=winner_id,
        loser_id=loser_id,
    )
    session.add(row)
    session.commit()
    return row


def add_backtest_run(
    session,
    *,
    id: int,
    stake: float = 1.0,
    dataset: str = "test_2026",
    dataset_start: datetime.date = datetime.date(2026, 1, 1),
    dataset_end: datetime.date = datetime.date(2026, 6, 1),
    n_matches: int = 2,
) -> BacktestRun:
    run = BacktestRun(
        id=id,
        dataset=dataset,
        dataset_start=dataset_start,
        dataset_end=dataset_end,
        n_matches=n_matches,
        models_fingerprint="test",
        model_source="tests",
        trained_through=datetime.date(2025, 12, 31),
        stake=stake,
    )
    session.add(run)
    session.commit()
    return run


def add_backtest_model_result(
    session,
    *,
    id: int,
    run_id: int,
    model: str,
    brier: float,
    is_benchmark: bool = False,
    n_scored: int = 10,
    log_loss: float = 0.5,
    accuracy: float = 0.6,
    n_bets: int = 0,
    n_bet_wins: int = 0,
    staked: float = 0.0,
    profit: float = 0.0,
    roi=None,
) -> BacktestModelResult:
    row = BacktestModelResult(
        id=id,
        run_id=run_id,
        model=model,
        is_benchmark=is_benchmark,
        n_scored=n_scored,
        brier=brier,
        log_loss=log_loss,
        accuracy=accuracy,
        n_bets=n_bets,
        n_bet_wins=n_bet_wins,
        staked=staked,
        profit=profit,
        roi=roi,
    )
    session.add(row)
    session.commit()
    return row


def add_backtest_match(
    session,
    *,
    id: int,
    run_id: int,
    row_index: int,
    match_date: datetime.date,
    surface: str = "Hard",
    player1: str = "A",
    player2: str = "B",
    player1_won: bool = True,
) -> BacktestMatch:
    row = BacktestMatch(
        id=id,
        run_id=run_id,
        row_index=row_index,
        match_date=match_date,
        player1=player1,
        player2=player2,
        surface=surface,
        player1_won=player1_won,
    )
    session.add(row)
    session.commit()
    return row


def add_backtest_prediction(
    session,
    *,
    id: int,
    run_id: int,
    match_id: int,
    model: str,
    prob_player1: float = 0.6,
    bet_side=None,
    bet_odds=None,
    bet_profit=None,
) -> BacktestPrediction:
    row = BacktestPrediction(
        id=id,
        run_id=run_id,
        match_id=match_id,
        model=model,
        prob_player1=prob_player1,
        bet_side=bet_side,
        bet_odds=bet_odds,
        bet_profit=bet_profit,
    )
    session.add(row)
    session.commit()
    return row
