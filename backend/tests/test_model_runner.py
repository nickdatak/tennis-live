"""Orientation averaging and the six-model load contract, with stub pipelines."""
from __future__ import annotations

import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import MODEL_FEATURE_COLUMNS, MODEL_FILENAMES
from app.services.feature_builder import PlayerState, build_feature_frame
from app.services.model_runner import ModelRunner


def make_player(*, elo_global: float, **overrides) -> PlayerState:
    values = dict(
        name="Player",
        elo_global=elo_global,
        surface_elos={"Hard": elo_global, "Clay": elo_global, "Grass": elo_global},
        surface_match_counts={"Hard": 10, "Clay": 10, "Grass": 10},
        rank=5.0,
        last_match_date=datetime.date(2026, 8, 1),
        recent_match_dates=[],
    )
    values.update(overrides)
    return PlayerState(**values)

PREDICTION_DATE = datetime.date(2026, 8, 29)
STRONGER = make_player(elo_global=2000.0, name="Strong", rank=1.0)
WEAKER = make_player(elo_global=1800.0, name="Weak", rank=20.0)


class FixedTwoRowPipeline:
    """Ignores features; returns predetermined P(class=1) for the two rows."""

    def __init__(self, p_row0: float, p_row1: float, classes=(0, 1)):
        self.classes_ = np.array(classes)
        self._p = np.array([p_row0, p_row1], dtype=float)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        assert len(features) == 2
        if list(self.classes_) == [0, 1]:
            return np.column_stack([1.0 - self._p, self._p])
        # class 1 lives in column 0
        return np.column_stack([self._p, 1.0 - self._p])


class SignBiasedPipeline:
    classes_ = np.array([0, 1])

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        favored = features["GlobalEloDiff"].to_numpy() >= 0
        p = np.where(favored, 0.80, 0.40)
        return np.column_stack([1.0 - p, p])


def _loaded(runner: ModelRunner, pipeline) -> ModelRunner:
    runner.pipelines = {name: pipeline for name in MODEL_FILENAMES}
    return runner


class TestLoad:
    def test_missing_files_raise(self, tmp_path):
        runner = ModelRunner()
        with patch("app.services.model_runner.MODELS_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="Missing model files"):
                runner.load()
        assert runner.is_loaded is False

    def test_feature_contract_mismatch_is_rejected(self, tmp_path):
        for filename in MODEL_FILENAMES.values():
            (tmp_path / filename).touch()

        class WrongFeatures:
            feature_names_in_ = ["not", "the", "contract"]

        runner = ModelRunner()
        with (
            patch("app.services.model_runner.MODELS_DIR", tmp_path),
            patch("app.services.model_runner.joblib.load", return_value=WrongFeatures()),
        ):
            with pytest.raises(AssertionError, match="feature contract"):
                runner.load()

    def test_is_loaded_only_when_all_six_are_present(self, tmp_path):
        for filename in MODEL_FILENAMES.values():
            (tmp_path / filename).touch()

        class Ok:
            feature_names_in_ = list(MODEL_FEATURE_COLUMNS)

        runner = ModelRunner()
        with (
            patch("app.services.model_runner.MODELS_DIR", tmp_path),
            patch("app.services.model_runner.joblib.load", return_value=Ok()),
        ):
            runner.load()
        assert runner.is_loaded
        assert set(runner.pipelines) == set(MODEL_FILENAMES)


class TestPredict:
    def test_refuses_to_run_before_load(self):
        runner = ModelRunner()
        with pytest.raises(AssertionError, match="Models not loaded"):
            runner.predict(STRONGER, WEAKER, "Hard", PREDICTION_DATE)

    def test_averages_both_orientations(self):
        # (0.90 + (1 - 0.30)) / 2 = 0.80
        runner = _loaded(ModelRunner(), FixedTwoRowPipeline(0.90, 0.30))
        result = runner.predict(STRONGER, WEAKER, "Hard", PREDICTION_DATE)
        assert result["mean"] == pytest.approx(0.80)
        assert all(
            value == pytest.approx(0.80) for value in result["per_model"].values()
        )
        assert set(result["per_model"]) == set(MODEL_FILENAMES)

    def test_positive_class_is_the_column_for_label_1_not_index_1(self):
        runner = _loaded(
            ModelRunner(), FixedTwoRowPipeline(0.90, 0.40, classes=(1, 0))
        )
        result = runner.predict(STRONGER, WEAKER, "Hard", PREDICTION_DATE)
        assert result["mean"] == pytest.approx(0.75)

    def test_averaged_probabilities_are_complementary_when_players_swap(self):
        runner = _loaded(ModelRunner(), SignBiasedPipeline())
        p_strong = runner.predict(STRONGER, WEAKER, "Hard", PREDICTION_DATE)["mean"]
        p_weak = runner.predict(WEAKER, STRONGER, "Hard", PREDICTION_DATE)["mean"]
        assert p_strong == pytest.approx(0.70)
        assert p_weak == pytest.approx(0.30)
        assert p_strong + p_weak == pytest.approx(1.0)

        # The raw (row-0) scores do not complement — that is why we average.
        pipeline = runner.pipelines["Decision Tree"]
        raw_ab = pipeline.predict_proba(
            build_feature_frame(STRONGER, WEAKER, "Hard", PREDICTION_DATE)
        )[0, 1]
        raw_ba = pipeline.predict_proba(
            build_feature_frame(WEAKER, STRONGER, "Hard", PREDICTION_DATE)
        )[0, 1]
        assert raw_ab + raw_ba == pytest.approx(1.20)

    def test_missing_rank_is_json_null_not_nan(self):
        runner = _loaded(ModelRunner(), FixedTwoRowPipeline(0.5, 0.5))
        unranked = make_player(elo_global=1800.0, name="U", rank=None)
        result = runner.predict(unranked, WEAKER, "Hard", PREDICTION_DATE)
        features = result["features_player1_first"]
        assert set(features) == set(MODEL_FEATURE_COLUMNS)
        assert features["RankDiff"] is None
        assert all(value is None or isinstance(value, float) for value in features.values())
        assert not any(
            isinstance(value, float) and np.isnan(value) for value in features.values()
        )

    def test_mean_is_the_mean_of_per_model(self):
        runner = ModelRunner()
        names = list(MODEL_FILENAMES)
        runner.pipelines = {
            names[0]: FixedTwoRowPipeline(0.90, 0.10),  # 0.90
            names[1]: FixedTwoRowPipeline(0.60, 0.40),  # 0.60
            names[2]: FixedTwoRowPipeline(0.50, 0.50),  # 0.50
            names[3]: FixedTwoRowPipeline(0.50, 0.50),
            names[4]: FixedTwoRowPipeline(0.50, 0.50),
            names[5]: FixedTwoRowPipeline(0.50, 0.50),
        }
        result = runner.predict(STRONGER, WEAKER, "Hard", PREDICTION_DATE)
        expected = np.mean(list(result["per_model"].values()))
        assert result["mean"] == pytest.approx(expected)
