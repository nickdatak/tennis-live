"""Read-only backtest endpoints.

These only query the tables written by backend/scripts/run_backtest.py — the
dashboard never runs models to produce a backtest. Rerun the script locally
when the models are replaced.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db.database import get_session
from ..db.models import BacktestMatch, BacktestModelResult, BacktestPrediction, BacktestRun
from ..schemas import (
    BacktestModelScore,
    BacktestSummary,
    EquityPoint,
    EquityResponse,
    EquitySeries,
)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


def _latest_run(session: Session) -> BacktestRun:
    run = session.scalars(
        select(BacktestRun).order_by(BacktestRun.id.desc()).limit(1)
    ).first()
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="No backtest stored. Run: python3 backend/scripts/run_backtest.py",
        )
    return run


@router.get("", response_model=BacktestSummary)
def backtest_summary(session: Session = Depends(get_session)) -> BacktestSummary:
    """Latest run metadata plus one row per model, best Brier score first."""
    run = _latest_run(session)
    rows = session.scalars(
        select(BacktestModelResult)
        .where(BacktestModelResult.run_id == run.id)
        .order_by(BacktestModelResult.brier.asc())
    ).all()
    return BacktestSummary(
        run_id=run.id,
        computed_at=run.created_at,
        dataset=run.dataset,
        dataset_start=run.dataset_start,
        dataset_end=run.dataset_end,
        n_matches=run.n_matches,
        trained_through=run.trained_through,
        model_source=run.model_source,
        stake=run.stake,
        models=[
            BacktestModelScore(
                model=row.model,
                is_benchmark=row.is_benchmark,
                n_scored=row.n_scored,
                brier=row.brier,
                log_loss=row.log_loss,
                accuracy=row.accuracy,
                n_bets=row.n_bets,
                n_bet_wins=row.n_bet_wins,
                staked=row.staked,
                profit=row.profit,
                roi=row.roi,
            )
            for row in rows
        ],
    )


@router.get("/equity", response_model=EquityResponse)
def equity_curves(
    surface: str = Query("All", max_length=20),
    session: Session = Depends(get_session),
) -> EquityResponse:
    """Running-ROI curve for every model, optionally restricted to one surface.

    All models are returned in a single response so the dashboard can toggle
    which ones are overlaid without another request.
    """
    run = _latest_run(session)

    if surface != "All":
        available = set(
            session.scalars(
                select(BacktestMatch.surface)
                .where(BacktestMatch.run_id == run.id)
                .distinct()
            ).all()
        )
        if surface not in available:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown surface {surface!r}. Available: All, "
                + ", ".join(sorted(s for s in available if s)),
            )

    placed = BacktestPrediction.bet_side.is_not(None)
    won = BacktestPrediction.bet_profit > 0

    # One row per model per day; the running totals are accumulated below so
    # the SQL stays simple and portable.
    statement = (
        select(
            BacktestPrediction.model,
            BacktestMatch.match_date,
            func.sum(BacktestPrediction.bet_profit),
            func.count(BacktestPrediction.id),
            func.sum(case((won, 1), else_=0)),
        )
        .join(BacktestMatch, BacktestPrediction.match_id == BacktestMatch.id)
        .where(BacktestPrediction.run_id == run.id, placed)
        .group_by(BacktestPrediction.model, BacktestMatch.match_date)
        .order_by(BacktestPrediction.model, BacktestMatch.match_date)
    )
    if surface != "All":
        statement = statement.where(BacktestMatch.surface == surface)

    by_model: dict[str, list] = {}
    for model, match_date, profit, n_bets, n_wins in session.execute(statement).all():
        by_model.setdefault(model, []).append(
            (match_date, float(profit or 0.0), int(n_bets), int(n_wins or 0))
        )

    series = []
    for model, rows in by_model.items():
        points, running_profit, running_bets, running_wins = [], 0.0, 0, 0
        for match_date, profit, n_bets, n_wins in rows:
            running_profit += profit
            running_bets += n_bets
            running_wins += n_wins
            points.append(
                EquityPoint(
                    date=match_date,
                    cumulative_profit=round(running_profit, 4),
                    cumulative_bets=running_bets,
                    roi=running_profit / (running_bets * run.stake),
                )
            )
        series.append(
            EquitySeries(
                model=model,
                n_bets=running_bets,
                n_wins=running_wins,
                profit=round(running_profit, 4),
                roi=running_profit / (running_bets * run.stake) if running_bets else None,
                points=points,
            )
        )

    series.sort(key=lambda item: item.roi if item.roi is not None else -9e9, reverse=True)
    return EquityResponse(
        run_id=run.id, surface=surface, stake=run.stake, series=series
    )
