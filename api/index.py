"""Vercel entry point: exposes the FastAPI app as an ASGI function.

Vercel routes /api/* here (see vercel.json); the dashboard itself is served
statically from frontend/ by the CDN.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402,F401  (Vercel detects the ASGI `app`)
