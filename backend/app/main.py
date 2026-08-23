"""FastAPI application: API under /api, static frontend served at /."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .api import bets, players, predict, refresh
from .config import FRONTEND_DIR, USING_DEV_SQLITE
from .db.database import SessionLocal, init_db
from .db.models import Player
from .schemas import HealthResponse
from .services.model_runner import model_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    model_runner.load()
    yield


app = FastAPI(title="Tennis Live", lifespan=lifespan)
app.include_router(players.router)
app.include_router(predict.router)
app.include_router(refresh.router)
app.include_router(bets.router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_status = "connected"
    players_in_db = None
    try:
        with SessionLocal() as session:
            players_in_db = session.scalar(select(func.count(Player.id)))
    except Exception as error:  # pragma: no cover - depends on external DB
        database_status = f"error: {type(error).__name__}"
    return HealthResponse(
        status="ok" if model_runner.is_loaded and database_status == "connected" else "degraded",
        models_loaded=len(model_runner.pipelines),
        database=database_status,
        using_dev_sqlite=USING_DEV_SQLITE,
        players_in_db=players_in_db,
    )


# Mounted last so /api keeps precedence. On Vercel the CDN serves the
# frontend and the directory may be absent from the function bundle.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
