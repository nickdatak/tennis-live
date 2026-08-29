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

CONFIG_ERRORS = []

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    CONFIG_ERRORS.append(
        "DATABASE_URL is not set and there is no local fallback. Put the "
        "Supabase pooler URI in backend/.env locally, or in the hosting "
        "platform's variables when deployed."
    )

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

PRODUCTION = os.environ.get("PRODUCTION", "").strip() in {"1", "true", "yes"}

_origins_raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()] or ["*"]
if PRODUCTION and ALLOWED_ORIGINS == ["*"]:
    CONFIG_ERRORS.append(
        "PRODUCTION=1 but ALLOWED_ORIGINS is not set; the API accepts requests "
        "from any origin. Set it to the frontend URL."
    )

SURFACE_DEBUT_ELO_MODE = os.environ.get("SURFACE_DEBUT_ELO_MODE", "initial").strip().lower()
assert SURFACE_DEBUT_ELO_MODE in {"initial", "as_given"}
