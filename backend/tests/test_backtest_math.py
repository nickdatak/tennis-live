"""Betting simulation and scoring — the math the dashboard stores, not the I/O."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import brier_score_loss, log_loss

from app.config import MODEL_FEATURE_COLUMNS
from app.services.feature_builder import swap_orientation

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
_SPEC = importlib.util.spec_from_file_location("run_backtest_script", _SCRIPT)
run_backtest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_backtest)

simulate_bets = run_backtest.simulate_bets
score_probabilities = run_backtest.score_probabilities
positive_probability = run_backtest.positive_probability
STAKE = run_backtest.STAKE


def test_score_probabilities_matches_sklearn():
    probabilities = np.array([0.9, 0.8, 0.1])
    outcomes = np.array([1, 0, 0])
    scores = score_probabilities(probabilities, outcomes)
    assert scores["n_scored"] == 3
    assert scores["brier"] == pytest.approx(brier_score_loss(outcomes, probabilities))
    assert scores["log_loss"] == pytest.approx(
        log_loss(outcomes, probabilities, labels=[0, 1])
    )
    assert scores["accuracy"] == pytest.approx(2 / 3)


def test_positive_probability_uses_the_class_1_column():
    class Pipeline:
        classes_ = np.array([1, 0])

        def predict_proba(self, features):
            return np.array([[0.8, 0.2], [0.3, 0.7]])

    features = pd.DataFrame([[0.0], [0.0]])
    assert positive_probability(Pipeline(), features).tolist() == pytest.approx(
        [0.8, 0.3]
    )


class TestSimulateBets:
    def test_no_bet_when_odds_missing_or_not_greater_than_one(self):
        bets = simulate_bets(
            probabilities=np.array([0.9, 0.9, 0.9]),
            player1_odds=np.array([np.nan, 1.0, 2.0]),
            player2_odds=np.array([2.0, 2.0, 1.0]),
            player1_won=np.array([1, 1, 1]),
        )
        assert bets["bet_side"].isna().all()
        assert bets["bet_profit"].isna().all()

    def test_no_bet_when_both_sides_have_non_positive_ev(self):
        # p=0.5, odds=1.5 both sides => EV = -0.25 each
        bets = simulate_bets(
            probabilities=np.array([0.5]),
            player1_odds=np.array([1.5]),
            player2_odds=np.array([1.5]),
            player1_won=np.array([1]),
        )
        assert bets["bet_side"].iloc[0] is None
        assert np.isnan(bets["bet_profit"].iloc[0])

    def test_backs_player1_on_tied_positive_ev(self):
        # p=0.6, odds=2.0 both sides => EV = 0.2 each; >= sends the tie to player1
        bets = simulate_bets(
            probabilities=np.array([0.6]),
            player1_odds=np.array([2.0]),
            player2_odds=np.array([2.0]),
            player1_won=np.array([1]),
        )
        assert bets["bet_side"].iloc[0] == "player1"
        assert bets["bet_odds"].iloc[0] == pytest.approx(2.0)
        assert bets["bet_profit"].iloc[0] == pytest.approx(2.0 - 1.0)

    def test_backs_higher_ev_side_and_losing_bet_costs_the_stake(self):
        bets = simulate_bets(
            probabilities=np.array([0.3]),
            player1_odds=np.array([1.5]),
            player2_odds=np.array([3.0]),
            player1_won=np.array([1]),
        )
        assert bets["bet_side"].iloc[0] == "player2"
        assert bets["bet_profit"].iloc[0] == pytest.approx(-STAKE)

    def test_player2_bet_wins_when_player1_loses(self):
        bets = simulate_bets(
            probabilities=np.array([0.3]),
            player1_odds=np.array([1.5]),
            player2_odds=np.array([3.0]),
            player1_won=np.array([0]),
        )
        assert bets["bet_side"].iloc[0] == "player2"
        assert bets["bet_profit"].iloc[0] == pytest.approx(3.0 - 1.0)


def test_swap_orientation_is_the_same_function_the_backtest_imports():
    assert run_backtest.swap_orientation is swap_orientation
    frame = pd.DataFrame(
        [[5.0, -1.0, 2.0, 1.0, 0.0, 3.0]],
        columns=MODEL_FEATURE_COLUMNS,
    )
    swapped = run_backtest.swap_orientation(frame)
    assert swapped["GlobalEloDiff"].iloc[0] == pytest.approx(-5.0)
    assert swapped["Player1LayoffOver6Months"].iloc[0] == pytest.approx(0.0)
