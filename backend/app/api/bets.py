"""Bet tracking placeholders — real endpoints arrive with the bets feature."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/bets", tags=["bets"])


@router.get("")
def list_bets() -> dict:
    return {"status": "not_implemented", "bets": []}


@router.post("", status_code=501)
def create_bet() -> dict:
    raise HTTPException(status_code=501, detail="Bet tracking is not implemented yet.")
