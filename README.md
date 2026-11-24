# Tennis Live

Tennis Live is a pre-match forecasting dashboard for ATP singles. Pick two players and a court surface to see an ensemble win probability, compare six models, and inspect the player data behind the forecast. The backtest shows how those model families performed on a chronological holdout and compares their probabilities with historical Bet365 prices.

**All rights reserved.** The [project license](LICENSE) permits viewing. Reuse requires prior written permission. The setup and deployment instructions are for maintainers and others with that permission.

![Alcaraz versus Sinner on clay, showing the ensemble forecast, all six model probabilities, player profiles, and model inputs](docs/screenshots/forecast.png)

*Example forecast from the snapshot through 14 August 2026, with 863 players and 28,425 completed matches.*

## Explore the dashboard

**Prediction.** Search for both players, choose Hard, Clay, or Grass, and run a forecast. The results show the ensemble probability for each player, the six individual predictions, and the exact feature values sent to the models. Player profiles show stored rank, global and surface Elo, match counts, and the date of the underlying snapshot. Head-to-head counts cover meetings in the imported match history.

![Player selection form with Alcaraz and Sinner selected on clay](docs/screenshots/matchup.png)

**Backtest.** Compare Brier score, log loss, accuracy, and simulated betting returns. The return chart supports all surfaces combined or separate Hard, Clay, and Grass views. The score table covers the full holdout.

![Backtest dashboard showing model scores and cumulative return on stake by model](docs/screenshots/backtest.png)

## How the forecast works

The six models are Decision Tree, Random Forest, XGBoost, LightGBM, Logistic Regression, and a simple neural network. Each pipeline takes the same six pre-match inputs.

| Input | Definition |
| --- | --- |
| `GlobalEloDiff` | Player 1's overall Elo minus Player 2's |
| `SurfaceEloDiff` | The same difference using Elo for the selected surface |
| `RankDiff` | Player 1's ATP rank minus Player 2's |
| `Player1LayoffOver6Months` | Whether Player 1's last recorded match was more than six calendar months earlier |
| `Player2LayoffOver6Months` | The corresponding flag for Player 2 |
| `MatchesLast7DaysDiff` | The difference in matches played in the preceding seven days, excluding the prediction day |

Each model scores the matchup in both player orders. The API converts both outputs to Player 1's perspective and averages them. Swapping the players therefore gives complementary probabilities. The ensemble is the unweighted mean of the six probabilities.

The research notebooks calculate overall and surface Elo chronologically. Matches on the same day share the start-of-day ratings, and only completed matches update Elo. The prediction API defaults to Elo 1500 for a player with zero matches on the selected surface. Each model pipeline imputes missing inputs with medians learned during training. Head-to-head history is shown for context. Bookmaker odds are used in the evaluation.

The app builds predictions from an imported player snapshot and the server's current date. Rankings, ratings, and recent history come from the imported snapshot. Check the data-through date before interpreting a forecast.

## Historical evaluation

The research uses 2015–2024 for initial training, 2025 for validation, and 2026 for holdout evaluation. The backtest scores **1,822 completed matches from 4 January to 14 August 2026** using models refitted through **16 November 2025**. The prediction dashboard loads the final models, which were refitted through 14 August 2026 after holdout evaluation.

Brier score is the mean squared difference between the predicted probabilities and the match outcomes. Log loss penalizes confidently wrong predictions. Lower is better for both. The table shows the best model by Brier score and the bookmaker benchmark from the dashboard backtest.

| Predictor | Matches scored | Brier score | Log loss |
| --- | ---: | ---: | ---: |
| Simple Neural Net | 1,822 | 0.21467 | 0.61684 |
| Bet365 normalized odds | 1,806 | 0.20431 | 0.59384 |

The bookmaker row uses matches with valid decimal odds for both players. On that same subset, the research notebook reports a Brier score of 0.21523 for the Simple Neural Net and 0.20431 for Bet365. These notebook model scores use a single player ordering. The dashboard backtest uses two-order averaging. See the [bookmaker benchmark CSV](research/models/bookmaker_benchmark_scores.csv).

The simulation stakes one unit when either side has positive estimated expected value at the recorded Bet365 odds. If both qualify, it selects the side with the higher expected value. Cumulative ROI is total simulated profit divided by total stakes to date. Across all surfaces, the six models finished this holdout with simulated returns between −10.56% and −7.17%, excluding commission and stake limits.

## Run locally

### 1. Install the dependencies

Use Python **3.12** and a fresh PostgreSQL database. The frontend is plain HTML, CSS, and JavaScript and is served by FastAPI.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

On macOS, XGBoost and LightGBM need the OpenMP runtime. With Homebrew, install it with `brew install libomp`.

### 2. Configure the database and frontend

Create `backend/.env` with your database connection string.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
```

For Supabase, copy the session pooler URI from the Connect dialog when using an IPv4-only network. See [Supabase's PostgreSQL connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).

For local development, edit `frontend/config.js` to use the same origin as FastAPI.

```js
window.TENNIS_API_BASE = "";
```

### 3. Seed the data

The player loader expects a `players.json` snapshot keyed by player slug. For a full player index, provide your own snapshot. To try a single matchup, save this two-player example as `players.json` at the repository root. The values are from the August 2026 snapshot, with Elo values rounded for readability.

```json
{
  "alcaraz_c": {
    "model_name": "Alcaraz C.",
    "rank": 2,
    "elo": {"overall": 2144.8, "hard": 2033.3, "clay": 2079.8, "grass": 1970.8},
    "matches": {"overall": 338, "hard": 184, "clay": 115, "grass": 39},
    "last_match_date": "2026-04-14",
    "as_of": "2026-08-14",
    "recent_matches": []
  },
  "sinner_j": {
    "model_name": "Sinner J.",
    "rank": 1,
    "elo": {"overall": 2264.3, "hard": 2210.4, "clay": 2043.1, "grass": 1977.2},
    "matches": {"overall": 420, "hard": 271, "clay": 105, "grass": 44},
    "last_match_date": "2026-07-12",
    "as_of": "2026-08-14",
    "recent_matches": []
  }
}
```

Use exact `Winner` or `Loser` names from the [prepared match CSV](research/data/output/matches_2015_onwards.csv) for `model_name` so the history importer can join the rows. Date values use `YYYY-MM-DD`. The example limits player search and head-to-head history to the two players. The backtest uses its own holdout CSV and still scores all 1,822 matches.

Run the seed scripts in this order on a dedicated development database. The loaders create tables as needed and replace existing data in their respective tables. `load_players.py` also accepts `--json PATH` for a snapshot stored elsewhere.

```bash
python backend/scripts/load_players.py
python backend/scripts/seed_match_history.py
python backend/scripts/run_backtest.py
```

### 4. Start the app

```bash
python backend/run.py
```

Open the [dashboard](http://127.0.0.1:8000/), [API health endpoint](http://127.0.0.1:8000/api/health), or [interactive API docs](http://127.0.0.1:8000/docs). A healthy startup reports a connected database and six loaded models.

## API

| Endpoint | Returns |
| --- | --- |
| `GET /api/health` | Model count, database status, player count, and latest imported match date |
| `GET /api/players?q=sinner&limit=8` | Player search by name or slug |
| `GET /api/players/all` | Player index used for autocomplete |
| `GET /api/players/compare?player1=alcaraz_c&player2=sinner_j&surface=Clay` | Both player profiles for a selected surface |
| `POST /api/predict` | Six model probabilities, ensemble mean, feature values, and head-to-head counts |
| `GET /api/backtest` | Latest stored holdout scores and simulation summary |
| `GET /api/backtest/equity?surface=Clay` | Per-model cumulative returns for a surface. Use `All` for the combined view. |

```bash
curl http://127.0.0.1:8000/api/predict \
  -H 'Content-Type: application/json' \
  -d '{"player1":"alcaraz_c","player2":"sinner_j","surface":"Clay"}'
```

## Repository layout

| Path | Contents |
| --- | --- |
| [`frontend/`](frontend/) | Dashboard and API base configuration |
| [`backend/app/`](backend/app/) | FastAPI routes, database models, feature builder, and inference |
| [`backend/models/`](backend/models/) | Six serialized pipelines used by the prediction API |
| [`backend/scripts/`](backend/scripts/) | Database seeding, backtest runner, and model synchronization |
| [`backend/tests/`](backend/tests/) | API, feature, inference, and backtest tests |
| [`research/`](research/) | Notebooks, match data, model artifacts, and evaluation outputs |

The research notebooks run in order from [data preparation](research/00_data_preparation.ipynb) through [Elo calculation](research/01_elo_calculation.ipynb), [feature creation](research/02_feature_creation.ipynb), [model training and evaluation](research/03_models.ipynb), and [permutation importance](research/04_feature_importance.ipynb). The [model manifest](research/models/model_manifest.csv) records the training and evaluation ranges for each artifact.

The shipped inference models are ready to load after installing dependencies. After re-exporting final research models, run `python backend/scripts/sync_models.py` to update the API copies. Keep the ML dependency pins aligned with the serialized models.

```bash
python -m pytest -q
```

To regenerate the match-level holdout predictions without a database, run `python backend/scripts/run_backtest.py --csv-only`. It writes `backend/data/backtest_predictions.csv`.

## Deployment

The repository includes a [Railway configuration](railway.json) for the API and a [Vercel configuration](vercel.json) for the static frontend.

1. Configure Railway from the repository root. It uses the root `requirements.txt` and starts `python3 backend/run.py`. Set `DATABASE_URL` and `PRODUCTION=1`. Set `ALLOWED_ORIGINS` to a comma-separated list of your frontend origins.
2. Seed the deployment database from a trusted environment and check that `/api/health` returns `status: ok`.
3. Set `window.TENNIS_API_BASE` in `frontend/config.js` to your public API origin. Deploy the `frontend/` directory through Vercel using the supplied configuration.

## Data and credits

Historical ATP match results and bookmaker odds are from [Tennis-Data](https://www.tennis-data.co.uk/data.php). The imported snapshot and research outputs represent the dataset available through 14 August 2026. Tennis-Data publishes separate terms for use of its spreadsheets.

Court photography by [Lester on Unsplash](https://unsplash.com/photos/aerial-view-of-white-and-blue-building-yoIt3Wxe0sI).
