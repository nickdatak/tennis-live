"""Thin Tennis API (RapidAPI) client with a hard per-run request budget."""
from __future__ import annotations

import datetime
import time
from typing import List, Optional

import httpx

from ..config import REFRESH_MAX_REQUESTS, TENNIS_API_HOST, TENNIS_API_KEY

MAIN_TOUR_TIERS = {"Grand Slam", "ATP Masters 1000", "ATP 500", "ATP 250", "Finals"}


class RequestBudgetExceeded(RuntimeError):
    pass


class TennisApiClient:
    """One instance per refresh run; counts every request against the budget."""

    def __init__(self, max_requests: int = REFRESH_MAX_REQUESTS):
        if not TENNIS_API_KEY:
            raise RuntimeError("TENNIS_API_KEY is not set in backend/.env")
        self.max_requests = max_requests
        self.requests_used = 0
        self._client = httpx.Client(
            base_url=f"https://{TENNIS_API_HOST}",
            headers={
                "X-RapidAPI-Key": TENNIS_API_KEY,
                "X-RapidAPI-Host": TENNIS_API_HOST,
            },
            timeout=30,
        )

    def close(self) -> None:
        self._client.close()

    # Space requests out and back off on 429s — refreshes are rare and small,
    # so being slow beats tripping the plan's rate limit.
    REQUEST_SPACING_SECONDS = 1.0
    BACKOFF_SECONDS = (5, 15, 30)

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        if self.requests_used >= self.max_requests:
            raise RequestBudgetExceeded(
                f"Refresh request budget of {self.max_requests} exhausted."
            )
        self.requests_used += 1
        time.sleep(self.REQUEST_SPACING_SECONDS)
        response = self._client.get(path, params=params or {})
        for backoff in self.BACKOFF_SECONDS:
            if response.status_code != 429:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                wait = max(float(retry_after), backoff) if retry_after else backoff
            except ValueError:
                wait = backoff
            time.sleep(min(wait, 60))
            response = self._client.get(path, params=params or {})
        response.raise_for_status()
        return response.json()

    def calendar_main_tour(
        self, year: int, since: datetime.date
    ) -> List[dict]:
        """All main-tour tournaments of `year` starting on/after `since`."""
        tournaments: List[dict] = []
        page = 1
        while True:
            payload = self._get(
                f"/tennis/v2/atp/tournament/calendar/{year}",
                {
                    "since": since.isoformat(),
                    "pageSize": 100,
                    "pageNo": page,
                    "include": "court,rank",
                },
            )
            rows = payload.get("data", [])
            tournaments.extend(t for t in rows if t.get("tier") in MAIN_TOUR_TIERS)
            if len(rows) < 100 or page >= 5:
                return tournaments
            page += 1

    def tournament_singles_results(self, season_id: int) -> List[dict]:
        """Main-draw singles rows for one tournament (qualifying excluded)."""
        payload = self._get(f"/tennis/v2/atp/tournament/results/{season_id}")
        body = payload.get("data", payload)
        return body.get("singles", []) if isinstance(body, dict) else []

    def rankings_singles(self, max_pages: int = 5, page_size: int = 100) -> List[dict]:
        """Current ATP singles rankings, top max_pages * page_size."""
        entries: List[dict] = []
        for page in range(1, max_pages + 1):
            payload = self._get(
                "/tennis/v2/atp/ranking/singles",
                {"pageSize": page_size, "pageNo": page},
            )
            rows = payload.get("data", [])
            entries.extend(rows)
            if len(rows) < page_size:
                break
        return entries
