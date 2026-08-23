"""Dev server entry point: python3 backend/run.py [port]"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
# Drop the ''/cwd-relative entries some launchers add; they break sandboxed imports.
sys.path[:] = [p for p in sys.path if p]

import uvicorn

from app.main import app

if __name__ == "__main__":
    import os

    # Hosting platforms inject PORT and need 0.0.0.0; local default stays loopback.
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    uvicorn.run(app, host=host, port=port, loop="asyncio", http="h11")
