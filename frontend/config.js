"use strict";

/* Deploy-time configuration. Edit this one line, redeploy the frontend.
 *
 * The API is a separate service now, so this must point at its origin, e.g.
 *   window.TENNIS_API_BASE = "https://tennis-live-api.up.railway.app";
 *
 * Leave it empty to call the same origin the page was served from. That is
 * what you want locally: `python3 backend/run.py` serves the frontend and the
 * API together on http://127.0.0.1:8000.
 */
window.TENNIS_API_BASE = "";
