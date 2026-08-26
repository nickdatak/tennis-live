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
    BacktestSurfaceBreakdown,
    EquityPoint,
    ModelBreakdownResponse,
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


@router.get("/model", response_model=ModelBreakdownResponse)
def model_breakdown(
    model: str = Query(..., min_length=1, max_length=64),
    session: Session = Depends(get_session),
) -> ModelBreakdownResponse:
    """Per-surface betting results and the cumulative profit curve for one model."""
    run = _latest_run(session)
    exists = session.scalar(
        select(func.count(BacktestModelResult.id)).where(
            BacktestModelResult.run_id == run.id, BacktestModelResult.model == model
        )
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"No results for model {model!r}.")

    placed = BacktestPrediction.bet_side.is_not(None)
    won = BacktestPrediction.bet_profit > 0

    surface_rows = session.execute(
        select(
            BacktestMatch.surface,
            func.count(BacktestPrediction.id),
            func.sum(case((won, 1), else_=0)),
            func.sum(BacktestPrediction.bet_profit),
        )
        .join(BacktestMatch, BacktestPrediction.match_id == BacktestMatch.id)
        .where(
            BacktestPrediction.run_id == run.id,
            BacktestPrediction.model == model,
            placed,
        )
        .group_by(BacktestMatch.surface)
        .order_by(BacktestMatch.surface)
    ).all()

    surfaces = [
        BacktestSurfaceBreakdown(
            surface=surface or "Unknown",
            n_bets=int(n_bets),
            n_wins=int(n_wins or 0),
            profit=float(profit or 0.0),
            roi=float(profit or 0.0) / (int(n_bets) * run.stake) if n_bets else None,
        )
        for surface, n_bets, n_wins, profit in surface_rows
    ]

    # Daily profit, accumulated in Python to keep the SQL portable.
    daily_rows = session.execute(
        select(
            BacktestMatch.match_date,
            func.sum(BacktestPrediction.bet_profit),
            func.count(BacktestPrediction.id),
        )
        .join(BacktestMatch, BacktestPrediction.match_id == BacktestMatch.id)
        .where(
            BacktestPrediction.run_id == run.id,
            BacktestPrediction.model == model,
            placed,
        )
        .group_by(BacktestMatch.match_date)
        .order_by(BacktestMatch.match_date)
    ).all()

    equity, running_profit, running_bets = [], 0.0, 0
    for match_date, profit, n_bets in daily_rows:
        running_profit += float(profit or 0.0)
        running_bets += int(n_bets)
        equity.append(
            EquityPoint(
                date=match_date,
                cumulative_profit=round(running_profit, 4),
                cumulative_bets=running_bets,
            )
        )

    return ModelBreakdownResponse(
        run_id=run.id, model=model, stake=run.stake, surfaces=surfaces, equity=equity
    )
