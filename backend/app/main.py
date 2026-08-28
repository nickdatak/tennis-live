"""FastAPI application: API under /api, static frontend served at /."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .api import backtest, players, predict
from .config import ALLOWED_ORIGINS, CONFIG_ERRORS, FRONTEND_DIR, USING_DEV_SQLITE
from .db.database import SessionLocal, init_db
from .db.models import MatchResult, Player
from .schemas import HealthResponse
from .services.model_runner import model_runner


# Startup failures are recorded, not raised: the app must stay alive so
# /api/health can report exactly what is broken.
startup_errors: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_errors.clear()
    startup_errors.extend(CONFIG_ERRORS)
    try:
        init_db()
    except Exception as error:
        startup_errors.append(f"database init: {type(error).__name__}: {error}"[:300])
    try:
        model_runner.load()
    except Exception as error:
        startup_errors.append(f"model load: {type(error).__name__}: {error}"[:300])
    yield


app = FastAPI(title="Tennis Live", lifespan=lifespan)

# The frontend is served from Vercel's CDN and calls this API cross-origin.
# No cookies or auth headers are involved, so credentials stay off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(players.router)
app.include_router(predict.router)
app.include_router(backtest.router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_status = "connected"
    players_in_db = None
    data_through = None
    try:
        with SessionLocal() as session:
            players_in_db = session.scalar(select(func.count(Player.id)))
            # The dashboard shows this as the data vintage: the snapshot is
            # static, so the newest stored match is exactly how current it is.
            data_through = session.scalar(select(func.max(MatchResult.date)))
    except Exception as error:  # pragma: no cover - depends on external DB
        database_status = f"error: {type(error).__name__}"
    healthy = (
        model_runner.is_loaded
        and database_status == "connected"
        and not startup_errors
    )
    return HealthResponse(
        status="ok" if healthy else "degraded",
        models_loaded=len(model_runner.pipelines),
        database=database_status,
        using_dev_sqlite=USING_DEV_SQLITE,
        players_in_db=players_in_db,
        data_through=data_through,
        startup_errors=list(startup_errors),
    )


# Mounted last so /api keeps precedence. In production the CDN serves the
# frontend, so this directory is usually absent; the mount exists so that
# `python3 backend/run.py` still serves the whole app from one origin locally.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
