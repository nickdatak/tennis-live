"""Central configuration: paths, environment, and the model feature contract."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
RESEARCH_MODELS_DIR = PROJECT_ROOT / "research" / "models"
MODELS_DIR = BACKEND_DIR / "models"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = BACKEND_DIR / "data"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); never overrides real env vars."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BACKEND_DIR / ".env")

# Supabase session-pooler URI goes in backend/.env as DATABASE_URL.
# Without it we fall back to a local SQLite file so development still works.
# Configuration problems are collected here instead of raising at import —
# a crashed serverless function cannot explain itself, /api/health can.
CONFIG_ERRORS = []

DEV_SQLITE_URL = f"sqlite:///{DATA_DIR / 'dev.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USING_DEV_SQLITE = not DATABASE_URL
if USING_DEV_SQLITE:
    if os.environ.get("PRODUCTION", "").strip() in {"1", "true", "yes"}:
        CONFIG_ERRORS.append(
            "PRODUCTION=1 but DATABASE_URL is not set. "
            "Set DATABASE_URL to the Supabase pooler URI and redeploy."
        )
    DATABASE_URL = DEV_SQLITE_URL

# The exact six-column contract every trained pipeline expects, in order.
MODEL_FEATURE_COLUMNS = [
    "GlobalEloDiff",
    "SurfaceEloDiff",
    "RankDiff",
    "Player1LayoffOver6Months",
    "Player2LayoffOver6Months",
    "MatchesLast7DaysDiff",
]

MODEL_FILENAMES = {
    "Decision Tree": "decision_tree.joblib",
    "Random Forest": "random_forest.joblib",
    "XGBoost": "xgboost.joblib",
    "LightGBM": "lightgbm.joblib",
    "Logistic Regression": "logistic_regression.joblib",
    "Simple Neural Net": "simple_neural_net.joblib",
}

SURFACES = ("Hard", "Clay", "Grass")
INITIAL_ELO = 1500.0

# Tennis API (RapidAPI: tennis-api-atp-wta-itf) — key lives in backend/.env.
TENNIS_API_KEY = os.environ.get("TENNIS_API_KEY", "").strip()
TENNIS_API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
# Hard ceiling per refresh run so a bug can never spray requests.
REFRESH_MAX_REQUESTS = 25

# Refresh is DISABLED by default to preserve Tennis API quota. Set
# REFRESH_ENABLED=1 to turn POST /api/refresh back on; the code is untouched.
REFRESH_ENABLED = os.environ.get("REFRESH_ENABLED", "").strip() in {"1", "true", "yes"}

# When set, POST /api/refresh requires this value in the X-Refresh-Token
# header. Set it on any public deployment — every refresh spends API quota.
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "").strip()

# Set PRODUCTION=1 on the hosting platform: refuses to boot without a real
# DATABASE_URL instead of silently using the ephemeral SQLite fallback.
PRODUCTION = os.environ.get("PRODUCTION", "").strip() in {"1", "true", "yes"}

# Elo parameters — must stay identical to research/01_elo_calculation.ipynb.
ELO_SCALE = 400.0
GLOBAL_BASE_K = 32.0
SURFACE_BASE_K = {"Hard": 32.0, "Clay": 40.0, "Grass": 52.0}
# API tier strings -> research tournament multipliers ("Finals" == Masters Cup).
TIER_MULTIPLIERS = {
    "Grand Slam": 1.00,
    "ATP Masters 1000": 1.05,
    "ATP 500": 0.95,
    "ATP 250": 0.90,
    "Finals": 1.00,
}
# API court names -> research surfaces (indoor variants collapse, as in training).
API_SURFACE_MAP = {
    "Hard": "Hard",
    "I.hard": "Hard",
    "Clay": "Clay",
    "I.clay": "Clay",
    "Grass": "Grass",
}

# Training semantics: a player's first match on a surface starts from Elo 1500.
# The seed JSON instead fills never-played surfaces with the player's overall
# Elo. "initial" (default) restores the training-faithful 1500 for surfaces
# with zero recorded matches; "as_given" trusts the JSON value.
SURFACE_DEBUT_ELO_MODE = os.environ.get("SURFACE_DEBUT_ELO_MODE", "initial").strip().lower()
assert SURFACE_DEBUT_ELO_MODE in {"initial", "as_given"}
