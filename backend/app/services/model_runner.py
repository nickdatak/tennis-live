"""Load the six trained pipelines once and serve orientation-averaged predictions."""
from __future__ import annotations

import datetime
from typing import Dict

import joblib
import numpy as np
import pandas as pd

from ..config import MODEL_FEATURE_COLUMNS, MODEL_FILENAMES, MODELS_DIR
from .feature_builder import PlayerState, build_feature_frame


class ModelRunner:
    def __init__(self):
        self.pipelines: Dict[str, object] = {}

    def load(self) -> None:
        missing = [
            filename
            for filename in MODEL_FILENAMES.values()
            if not (MODELS_DIR / filename).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"Missing model files in {MODELS_DIR}: {missing}. "
                "Run: python3 backend/scripts/sync_models.py"
            )
        for model_name, filename in MODEL_FILENAMES.items():
            pipeline = joblib.load(MODELS_DIR / filename)
            features_in = list(getattr(pipeline, "feature_names_in_", []))
            assert features_in == MODEL_FEATURE_COLUMNS, (
                f"{model_name} feature contract mismatch: {features_in}"
            )
            self.pipelines[model_name] = pipeline

    @property
    def is_loaded(self) -> bool:
        return len(self.pipelines) == len(MODEL_FILENAMES)

    @staticmethod
    def _positive_probability(pipeline, features: pd.DataFrame) -> np.ndarray:
        classes = np.asarray(pipeline.classes_)
        positive_indices = np.flatnonzero(classes == 1)
        assert len(positive_indices) == 1, f"Unexpected classes: {classes}"
        probabilities = np.asarray(pipeline.predict_proba(features))[
            :, int(positive_indices[0])
        ]
        assert probabilities.shape == (len(features),)
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0.0) & (probabilities <= 1.0)).all()
        return probabilities

    def predict(
        self,
        player1: PlayerState,
        player2: PlayerState,
        surface: str,
        prediction_date: datetime.date,
    ) -> dict:
        """Return per-model and mean P(player1 wins), symmetrized over orientation."""
        assert self.is_loaded, "Models not loaded; call load() at startup."
        features = build_feature_frame(player1, player2, surface, prediction_date)

        per_model = {}
        for model_name, pipeline in self.pipelines.items():
            probs = self._positive_probability(pipeline, features)
            # Row 0 is P(player1 wins); row 1 is P(player2 wins) in the
            # swapped orientation, so 1 - row1 is a second estimate of row 0.
            symmetrized = float((probs[0] + (1.0 - probs[1])) / 2.0)
            per_model[model_name] = symmetrized

        mean_probability = float(np.mean(list(per_model.values())))
        return {
            "per_model": per_model,
            "mean": mean_probability,
            "features_player1_first": {
                column: (None if pd.isna(value) else float(value))
                for column, value in features.iloc[0].items()
            },
        }


model_runner = ModelRunner()
