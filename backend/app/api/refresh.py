"""Refresh endpoint: pull new results + rankings from the Tennis API."""
from __future__ import annotations

import hmac
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db.database import get_session
from ..db.models import RefreshLog
from ..services.refresh import RefreshInProgress, run_refresh
from ..services.tennis_api import RequestBudgetExceeded

router = APIRouter(prefix="/api/refresh", tags=["refresh"])


@router.post("")
def refresh(
    session: Session = Depends(get_session),
    x_refresh_token: Optional[str] = Header(default=None),
) -> dict:
    # Every refresh spends Tennis API quota; on public deployments the
    # endpoint is gated by REFRESH_TOKEN.
    if config.REFRESH_TOKEN:
        if not x_refresh_token or not hmac.compare_digest(
            x_refresh_token, config.REFRESH_TOKEN
        ):
            raise HTTPException(
                status_code=401, detail="Missing or invalid X-Refresh-Token."
            )
    try:
        return run_refresh(session)
    except RefreshInProgress as error:
        raise HTTPException(status_code=409, detail=str(error))
    except RequestBudgetExceeded as error:
        raise HTTPException(status_code=502, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Tennis API error: HTTP {error.response.status_code}",
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Tennis API unreachable: {error}")


@router.get("/last")
def last_refresh(session: Session = Depends(get_session)) -> dict:
    log = session.scalars(
        select(RefreshLog).order_by(RefreshLog.id.desc()).limit(1)
    ).first()
    if log is None:
        return {"status": "never"}
    return {
        "status": log.status,
        "ran_at": log.ran_at.isoformat() if log.ran_at else None,
        "window_start": log.window_start.isoformat(),
        "window_end": log.window_end.isoformat(),
        "matches_applied": log.matches_applied,
        "retired_skipped": log.retired_skipped,
        "new_players": log.new_players,
        "rank_updates": log.rank_updates,
        "requests_used": log.requests_used,
        "detail": log.detail,
    }
