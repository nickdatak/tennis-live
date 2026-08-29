"""FastAPI application: API under /api, static frontend served at /."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .api import backtest, players, predict
from .config import ALLOWED_ORIGINS, CONFIG_ERRORS, FRONTEND_DIR
from .db.database import NO_DATABASE, SessionLocal, missing_tables
from .db.models import MatchResult, Player
from .schemas import HealthResponse
from .services.model_runner import model_runner


startup_errors: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_errors.clear()
    startup_errors.extend(CONFIG_ERRORS)
    try:
        absent = missing_tables()
        if absent:
            startup_errors.append(
                "missing tables: " + ", ".join(absent)
                + ". Run the seeding scripts in backend/scripts/."
            )
    except Exception as error:
        startup_errors.append(f"schema check: {type(error).__name__}: {error}"[:300])
    try:
        model_runner.load()
    except Exception as error:
        startup_errors.append(f"model load: {type(error).__name__}: {error}"[:300])
    yield


app = FastAPI(title="Tennis Live", lifespan=lifespan)

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
        if SessionLocal is None:
            raise RuntimeError(NO_DATABASE)
        with SessionLocal() as session:
            players_in_db = session.scalar(select(func.count(Player.id)))
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
        players_in_db=players_in_db,
        data_through=data_through,
        startup_errors=list(startup_errors),
    )


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
