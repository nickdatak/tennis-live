"""Stdlib-only diagnostic endpoint: /api/probe.

Imports nothing from the app at module level, so it cannot crash on deploy.
Reports what the serverless runtime actually sees: bundled files, env-var
presence (names only, never values), and the full traceback if importing the
real app fails.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import traceback
from pathlib import Path


def diagnose() -> dict:
    root = Path(__file__).resolve().parents[1]
    report = {
        "python": sys.version,
        "cwd": os.getcwd(),
        "root": str(root),
        "root_listing": sorted(p.name for p in root.iterdir())[:40],
        "backend_exists": (root / "backend").is_dir(),
        "backend_app_exists": (root / "backend" / "app").is_dir(),
        "models_dir_listing": None,
        "env_vars_present": sorted(
            k for k in ("DATABASE_URL", "PRODUCTION", "REFRESH_TOKEN", "TENNIS_API_KEY")
            if os.environ.get(k)
        ),
        "app_import": None,
    }
    models_dir = root / "backend" / "models"
    if models_dir.is_dir():
        report["models_dir_listing"] = sorted(p.name for p in models_dir.iterdir())

    try:
        sys.path.insert(0, str(root / "backend"))
        from app.main import app  # noqa: F401
        report["app_import"] = "ok"
    except BaseException:
        report["app_import"] = traceback.format_exc()[-2000:]
    return report


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = json.dumps(diagnose(), indent=1, default=str).encode()
        except BaseException:
            body = traceback.format_exc().encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
