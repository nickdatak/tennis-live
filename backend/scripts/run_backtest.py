from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss
from sqlalchemy import insert, select

from app.config import MODEL_FEATURE_COLUMNS, MODEL_FILENAMES, PROJECT_ROOT
from app.db.database import SessionLocal, init_db
from app.db.models import (
    BacktestMatch,
    BacktestModelResult,
    BacktestPrediction,
    BacktestRun,
)
from app.services.feature_builder import swap_orientation

RESEARCH_DIR = PROJECT_ROOT / "research"
HOLDOUT_MODEL_DIR = RESEARCH_DIR / "models" / "holdout_2026"
MANIFEST_PATH = RESEARCH_DIR / "models" / "model_manifest.csv"
TEST_SPLIT_PATH = RESEARCH_DIR / "data" / "output" / "model_test_2026.csv"
ELO_MATCHES_PATH = RESEARCH_DIR / "data" / "output" / "matches_2015_onwards_with_elo.csv"
CSV_OUTPUT_PATH = PROJECT_ROOT / "backend" / "data" / "backtest_predictions.csv"

DATASET_NAME = "test_2026"
STAKE = 1.0
RANDOM_SEED = 42  # must match research/02_feature_creation.ipynb
LAYOFF_COLUMNS = ["Player1LayoffOver6Months", "Player2LayoffOver6Months"]


def models_fingerprint() -> str:
    """Combined sha256 of the scored joblib files, so unchanged models are detectable."""
    digest = hashlib.sha256()
    for filename in sorted(MODEL_FILENAMES.values()):
        digest.update(filename.encode())
        digest.update((HOLDOUT_MODEL_DIR / filename).read_bytes())
    return digest.hexdigest()


def load_test_split() -> pd.DataFrame:
    frame = pd.read_csv(TEST_SPLIT_PATH, parse_dates=["Date"], low_memory=False)
    for column in LAYOFF_COLUMNS:
        frame[column] = (
            frame[column].astype("string").map({"True": 1.0, "False": 0.0}).astype(float)
        )
    for column in MODEL_FEATURE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def recover_match_context(test_frame: pd.DataFrame) -> pd.DataFrame:
    matches = pd.read_csv(ELO_MATCHES_PATH, parse_dates=["Date"], low_memory=False)
    is_valid = (
        matches["Comment"].eq("Completed")
        & matches[["Date", "Winner", "Loser"]].notna().all(axis=1)
    )
    source = matches.loc[is_valid].sort_values("Date", kind="stable")

    rng = np.random.default_rng(RANDOM_SEED)
    winner_is_player1 = pd.Series(
        rng.integers(0, 2, size=len(source), dtype=np.int8).astype(bool),
        index=source.index,
    )

    player1_elo = source["WinnerGlobalEloPre"].where(
        winner_is_player1, source["LoserGlobalEloPre"]
    )
    player2_elo = source["LoserGlobalEloPre"].where(
        winner_is_player1, source["WinnerGlobalEloPre"]
    )
    recovered = pd.DataFrame(
        {
            "Date": source["Date"].values,
            "GlobalEloDiff": (player1_elo - player2_elo).values,
            "Player1Won": winner_is_player1.astype("int8").values,
            "Player1": source["Winner"].where(winner_is_player1, source["Loser"]).values,
            "Player2": source["Loser"].where(winner_is_player1, source["Winner"]).values,
            "Surface": source["Surface"].values,
            "Series": source["Series"].values,
            "Tournament": source["Tournament"].values,
        }
    ).reset_index(drop=True)

    start, end = test_frame["Date"].min(), test_frame["Date"].max()
    recovered = recovered.loc[recovered["Date"].between(start, end)].reset_index(drop=True)

    assert len(recovered) == len(test_frame), (
        f"Recovered {len(recovered)} rows for {len(test_frame)} scored matches."
    )
    assert recovered["Date"].equals(test_frame["Date"]), "Recovered dates diverge."
    assert (
        recovered["Player1Won"].to_numpy() == test_frame["Player1Won"].to_numpy()
    ).all(), "Recovered outcomes diverge."
    assert np.allclose(
        recovered["GlobalEloDiff"].to_numpy(),
        test_frame["GlobalEloDiff"].to_numpy(),
        atol=1e-9,
    ), "Recovered Elo differences diverge; the orientation replay is wrong."
    return recovered


def bulk_insert(session, model_class, rows: list, chunk_size: int = 500) -> None:
    table = model_class.__table__
    for start in range(0, len(rows), chunk_size):
        session.execute(insert(table), rows[start : start + chunk_size])


def positive_probability(pipeline, features: pd.DataFrame) -> np.ndarray:
    classes = np.asarray(pipeline.classes_)
    positive_index = int(np.flatnonzero(classes == 1)[0])
    probabilities = np.asarray(pipeline.predict_proba(features))[:, positive_index]
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0.0) & (probabilities <= 1.0)).all()
    return probabilities


def simulate_bets(
    probabilities: np.ndarray,
    player1_odds: np.ndarray,
    player2_odds: np.ndarray,
    player1_won: np.ndarray,
) -> pd.DataFrame:
    """Back the higher-expected-value side when its expected value is positive."""
    priced = (
        np.isfinite(player1_odds)
        & np.isfinite(player2_odds)
        & (player1_odds > 1.0)
        & (player2_odds > 1.0)
    )
    ev_player1 = probabilities * player1_odds - 1.0
    ev_player2 = (1.0 - probabilities) * player2_odds - 1.0

    back_player1 = priced & (ev_player1 >= ev_player2) & (ev_player1 > 0.0)
    back_player2 = priced & (ev_player2 > ev_player1) & (ev_player2 > 0.0)

    side = np.where(back_player1, "player1", np.where(back_player2, "player2", None))
    odds = np.where(back_player1, player1_odds, np.where(back_player2, player2_odds, np.nan))
    bet_won = (back_player1 & (player1_won == 1)) | (back_player2 & (player1_won == 0))
    placed = back_player1 | back_player2
    profit = np.where(placed, np.where(bet_won, odds - 1.0, -STAKE), np.nan)

    return pd.DataFrame({"bet_side": side, "bet_odds": odds, "bet_profit": profit})


def score_probabilities(probabilities: np.ndarray, outcomes: np.ndarray) -> dict:
    return {
        "n_scored": int(len(outcomes)),
        "brier": float(brier_score_loss(outcomes, probabilities)),
        "log_loss": float(log_loss(outcomes, probabilities, labels=[0, 1])),
        "accuracy": float(((probabilities >= 0.5).astype(int) == outcomes).mean()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rerun even if the models are unchanged since the stored run.",
    )
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Write the CSV artifact without touching the database.",
    )
    args = parser.parse_args()

    import joblib

    assert HOLDOUT_MODEL_DIR.is_dir(), f"Missing {HOLDOUT_MODEL_DIR}"
    fingerprint = models_fingerprint()

    test_frame = load_test_split()
    outcomes = test_frame["Player1Won"].astype(int).to_numpy()
    features = test_frame[MODEL_FEATURE_COLUMNS]
    swapped_features = swap_orientation(features)
    context = recover_match_context(test_frame)
    print(
        f"Scoring {len(test_frame):,} matches "
        f"({test_frame['Date'].min():%Y-%m-%d} to {test_frame['Date'].max():%Y-%m-%d})"
    )
    print("Match context recovered and verified against the split file.")

    # Skip a pointless rerun unless forced: the results are deterministic.
    if not args.csv_only:
        init_db()
        with SessionLocal() as session:
            existing = (
                session.query(BacktestRun)
                .filter(BacktestRun.dataset == DATASET_NAME)
                .order_by(BacktestRun.id.desc())
                .first()
            )
            if existing and existing.models_fingerprint == fingerprint and not args.force:
                print(
                    f"Models unchanged since run #{existing.id} "
                    f"({existing.created_at:%Y-%m-%d %H:%M}). Nothing to do; "
                    "pass --force to rerun anyway."
                )
                return

    player1_odds = pd.to_numeric(test_frame["B365Player1Odds"], errors="coerce").to_numpy()
    player2_odds = pd.to_numeric(test_frame["B365Player2Odds"], errors="coerce").to_numpy()

    manifest = pd.read_csv(MANIFEST_PATH).set_index("Model")["HoldoutBrierScore"]
    results, prediction_frames = [], {}

    for model_name, filename in MODEL_FILENAMES.items():
        pipeline = joblib.load(HOLDOUT_MODEL_DIR / filename)
        assert list(pipeline.feature_names_in_) == MODEL_FEATURE_COLUMNS, model_name

        single_orientation = positive_probability(pipeline, features)
        single_brier = float(brier_score_loss(outcomes, single_orientation))
        assert np.isclose(single_brier, manifest.loc[model_name], atol=1e-9), (
            f"{model_name}: Brier {single_brier:.6f} != "
            f"manifest {manifest.loc[model_name]:.6f}"
        )

        # Score what the API serves: the orientation-averaged probability.
        probabilities = (
            single_orientation
            + (1.0 - positive_probability(pipeline, swapped_features))
        ) / 2.0
        scores = score_probabilities(probabilities, outcomes)

        bets = simulate_bets(probabilities, player1_odds, player2_odds, outcomes)
        placed = bets["bet_side"].notna()
        results.append(
            {
                "model": model_name,
                "is_benchmark": False,
                **scores,
                "n_bets": int(placed.sum()),
                "n_bet_wins": int((bets.loc[placed, "bet_profit"] > 0).sum()),
                "staked": float(placed.sum() * STAKE),
                "profit": float(bets.loc[placed, "bet_profit"].sum()),
                "roi": (
                    float(bets.loc[placed, "bet_profit"].sum() / (placed.sum() * STAKE))
                    if placed.any()
                    else None
                ),
            }
        )
        prediction_frames[model_name] = pd.DataFrame(
            {"prob_player1": probabilities, **bets}
        )
        print(
            f"  {model_name:22s} Brier={scores['brier']:.5f} "
            f"(one orientation {single_brier:.5f})  bets={int(placed.sum()):4d}"
        )

    # Bet365 as a predictor benchmark: overround-normalised implied probability.
    priced = np.isfinite(player1_odds) & np.isfinite(player2_odds)
    priced &= (player1_odds > 1.0) & (player2_odds > 1.0)
    implied1, implied2 = 1.0 / player1_odds[priced], 1.0 / player2_odds[priced]
    bookmaker_probabilities = implied1 / (implied1 + implied2)
    bookmaker_scores = score_probabilities(bookmaker_probabilities, outcomes[priced])
    results.append(
        {
            "model": "Bet365 (normalised odds)",
            "is_benchmark": True,
            **bookmaker_scores,
            "n_bets": 0,
            "n_bet_wins": 0,
            "staked": 0.0,
            "profit": 0.0,
            "roi": None,
        }
    )
    print(f"  {'Bet365 benchmark':22s} Brier={bookmaker_scores['brier']:.5f}")

    # Audit artifact: one row per model per match.
    long_rows = []
    for model_name, frame in prediction_frames.items():
        block = context[["Date", "Player1", "Player2", "Surface", "Series", "Player1Won"]].copy()
        block["Model"] = model_name
        block["B365Player1Odds"] = player1_odds
        block["B365Player2Odds"] = player2_odds
        long_rows.append(pd.concat([block, frame], axis=1))
    long_frame = pd.concat(long_rows, ignore_index=True)
    CSV_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    long_frame.to_csv(CSV_OUTPUT_PATH, index=False)
    print(f"Wrote {len(long_frame):,} rows to {CSV_OUTPUT_PATH}")

    if args.csv_only:
        print("--csv-only: database untouched.")
        return

    with SessionLocal() as session:
        # Replace: the tables hold the current backtest, not a history.
        removed = session.query(BacktestRun).filter(
            BacktestRun.dataset == DATASET_NAME
        ).delete(synchronize_session=False)
        session.flush()

        run = BacktestRun(
            dataset=DATASET_NAME,
            dataset_start=test_frame["Date"].min().date(),
            dataset_end=test_frame["Date"].max().date(),
            n_matches=len(test_frame),
            models_fingerprint=fingerprint,
            model_source="research/models/holdout_2026",
            trained_through=pd.Timestamp(
                pd.read_csv(MANIFEST_PATH)["EvaluationTrainedThrough"].iloc[0]
            ).date(),
            stake=STAKE,
        )
        session.add(run)
        session.flush()

        for row in results:
            session.add(BacktestModelResult(run_id=run.id, **row))

        def optional_float(value):
            return float(value) if np.isfinite(value) else None

        match_rows = [
            {
                "run_id": run.id,
                "row_index": position,
                "match_date": row.Date.date(),
                "player1": row.Player1,
                "player2": row.Player2,
                "surface": row.Surface if pd.notna(row.Surface) else None,
                "series": row.Series if pd.notna(row.Series) else None,
                "tournament": row.Tournament if pd.notna(row.Tournament) else None,
                "player1_won": bool(row.Player1Won),
                "b365_p1_odds": optional_float(player1_odds[position]),
                "b365_p2_odds": optional_float(player2_odds[position]),
            }
            for position, row in enumerate(context.itertuples(index=False))
        ]
        bulk_insert(session, BacktestMatch, match_rows)

        match_id_by_index = dict(
            session.execute(
                select(BacktestMatch.row_index, BacktestMatch.id).where(
                    BacktestMatch.run_id == run.id
                )
            ).all()
        )
        assert len(match_id_by_index) == len(match_rows)

        prediction_rows = [
            {
                "run_id": run.id,
                "match_id": match_id_by_index[position],
                "model": model_name,
                "prob_player1": float(prediction.prob_player1),
                "bet_side": prediction.bet_side,
                "bet_odds": float(prediction.bet_odds)
                if pd.notna(prediction.bet_odds)
                else None,
                "bet_profit": float(prediction.bet_profit)
                if pd.notna(prediction.bet_profit)
                else None,
            }
            for model_name, frame in prediction_frames.items()
            for position, prediction in enumerate(frame.itertuples(index=False))
        ]
        bulk_insert(session, BacktestPrediction, prediction_rows)

        session.commit()
        print(
            f"Replaced {removed} previous run(s); stored run #{run.id}: "
            f"{len(results)} model rows, {len(context):,} matches, "
            f"{len(long_frame):,} predictions."
        )


if __name__ == "__main__":
    main()
