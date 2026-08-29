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

# Supabase (pooler URI in DATABASE_URL) is the only database.
#
# The local SQLite fallback was removed rather than kept as a convenience: it
# did not enforce foreign keys -- SQLite defaults PRAGMA foreign_keys to OFF
# and nothing here turned it on -- so the match_results -> players constraint
# that stops load_players.py renumbering seeded player ids simply did not
# exist locally. Dev and production disagreed on the one behaviour that
# matters most, which is worse than having no local database at all.
#
# Configuration problems are collected here instead of raising at import —
# a process that dies during import cannot explain itself, /api/health can.
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

# The database holds a static snapshot of the research dataset (tennis-data.co.uk),
# current through the last stored match. There is no live ingest: no free odds+
# results feed covers the six-feature contract, and a paid one is out of scope
# here. The intended next step is a scheduled job (every ~6h) that appends new
# results and replays the research Elo update against this same schema.

# Set PRODUCTION=1 on the hosting platform: refuses to boot without a real
# DATABASE_URL instead of silently using the ephemeral SQLite fallback.
PRODUCTION = os.environ.get("PRODUCTION", "").strip() in {"1", "true", "yes"}

# The API and the frontend are now separate origins (API on Railway, static
# frontend on Vercel's CDN), so the browser requires CORS. Comma-separated
# list in ALLOWED_ORIGINS, e.g. "https://tennis-live.vercel.app".
# There are no cookies and no auth, so "*" is safe but sloppy: warn in prod.
_origins_raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()] or ["*"]
if PRODUCTION and ALLOWED_ORIGINS == ["*"]:
    CONFIG_ERRORS.append(
        "PRODUCTION=1 but ALLOWED_ORIGINS is not set; the API accepts requests "
        "from any origin. Set it to the frontend URL."
    )

# Training semantics: a player's first match on a surface starts from Elo 1500.
# The seed JSON instead fills never-played surfaces with the player's overall
# Elo. "initial" (default) restores the training-faithful 1500 for surfaces
# with zero recorded matches; "as_given" trusts the JSON value.
SURFACE_DEBUT_ELO_MODE = os.environ.get("SURFACE_DEBUT_ELO_MODE", "initial").strip().lower()
assert SURFACE_DEBUT_ELO_MODE in {"initial", "as_given"}
