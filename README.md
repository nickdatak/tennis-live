# Tennis Live

Live dashboard for predicting ATP match outcomes with the six models trained in
`research/`. Type two player names, pick a surface, and get six win
probabilities plus their mean. Bet tracking is planned (placeholders in place).

## Layout

```
research/    # notebooks + trained models — read-only, never modified by the app
backend/     # FastAPI API, feature builder, model runner, DB layer, scripts
frontend/    # plain HTML/CSS/JS dashboard, served by the backend at /
players.json # seed snapshot of player state (Elo, rank, recent matches)
```

## Setup

```bash
python3 -m pip install --user -r backend/requirements.txt

# 1. Copy the trained models out of research/ (never modifies research/)
python3 backend/scripts/sync_models.py

# 2. Point the app at Supabase (optional — falls back to local SQLite without it)
cp backend/.env.example backend/.env   # then paste your session-pooler URI

# 3. Create tables + seed players (works for both Supabase and dev SQLite)
python3 backend/scripts/load_players.py

# 4. Run
python3 -m uvicorn app.main:app --app-dir backend --port 8000
```

Dashboard: http://localhost:8000 · Health: http://localhost:8000/api/health

For Supabase you can also create the tables by pasting
`backend/app/db/schema.sql` into the SQL editor (the seed script otherwise
creates them itself).

## API

| Endpoint | Description |
|---|---|
| `GET /api/players?q=alc` | Case-insensitive player search (autocomplete) |
| `POST /api/predict` | `{player1, player2, surface}` → 6 probabilities + mean + H2H |
| `POST /api/refresh` | Pull new results + rankings from the Tennis API |
| `GET /api/refresh/last` | Last refresh run summary |
| `GET /api/health` | Models loaded, DB connectivity, player count |
| `GET/POST /api/bets` | Placeholders (not implemented yet) |

Predictions are **orientation-averaged**: each model scores both player
orderings and the results are combined, so swapping the inputs gives exactly
mirrored probabilities.

## Model/feature contract

The six pipelines expect exactly:
`GlobalEloDiff, SurfaceEloDiff, RankDiff, Player1LayoffOver6Months,
Player2LayoffOver6Months, MatchesLast7DaysDiff` — built at request time from
the players table using the same semantics as training (7-day workload window
excludes the prediction day; layoff is >6 calendar months; a surface the
player never played starts at Elo 1500 — configurable via
`SURFACE_DEBUT_ELO_MODE`).

ML library versions in `backend/requirements.txt` are pinned to the training
environment; bumping them can silently break joblib unpickling.

## Tests

```bash
python3 -m pytest backend/tests -q
```

## Data refresh

**Currently disabled to preserve Tennis API quota** — the endpoint returns
503 and the dashboard button reports it. Re-enable by setting
`REFRESH_ENABLED=1` (plus `TENNIS_API_KEY` and, on public deployments,
`REFRESH_TOKEN`). All code paths are intact.

The **⟳ Refresh data** button pulls everything new since the last processed
date from the Tennis API (RapidAPI: `tennis-api-atp-wta-itf`, key in
`backend/.env` as `TENNIS_API_KEY`):

- Main-tour singles results only (tiers: Grand Slam, Masters 1000, 500, 250,
  Finals; qualifying and Challengers excluded — matches training data)
- **Retired/walkover matches update nothing** (`result_type != "completed"`)
  — the models were not trained on them, by design
- Elo updated with the exact research rules (tier K-multipliers, surface K,
  same-day batching from start-of-day ratings)
- Match counts, last-match dates, 7-day workload history
- Current ATP rankings overwrite stored ranks
- Completed matches stored in `match_results` for H2H display (never a model
  input); history back to 2015 is seeded from the research dataset via
  `backend/scripts/seed_match_history.py`

Safety: hard cap of 25 API requests per refresh, 1s spacing, backoff on 429,
one transaction (all-or-nothing), dedup by API match id, and a refresh log
(`GET /api/refresh/last`).

## Later

- Bet tracking (tables and endpoints are stubbed)
