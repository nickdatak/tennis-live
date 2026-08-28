"use strict";

/* Deploy-time configuration: the origin of the API service.
 *
 * !! Use Railway's PUBLIC domain, not its private one. !!
 *
 *   WRONG   https://tennis-live.railway.internal
 *           *.railway.internal only resolves INSIDE Railway's project network
 *           (service-to-service, IPv6, plain HTTP). A browser gets NXDOMAIN,
 *           so every API call fails before it is even sent.
 *
 *   RIGHT   https://<service>-production-<hash>.up.railway.app
 *           Railway does not create this automatically. Generate it under
 *           Settings -> Networking -> Generate Domain.
 *
 * Leave empty to call the same origin the page was served from. That is what
 * you want locally: `python3 backend/run.py` serves the frontend and the API
 * together on http://127.0.0.1:8000.
 */
window.TENNIS_API_BASE = "https://tennis-live-production.up.railway.app";
