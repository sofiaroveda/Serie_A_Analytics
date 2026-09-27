"""Tests for the scoring rules."""

import numpy as np
import pandas as pd
import pytest

from pipeline.evaluate import base_rate_forecast, brier, compare_with_market, log_loss, rps


def test_perfect_forecast_scores_zero():
    probs = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]])
    results = ["H", "D", "A"]
    assert rps(probs, results) == 0 and brier(probs, results) == 0
    assert log_loss(probs, results) == pytest.approx(0, abs=1e-12)


def test_rps_hand_calculation():
    # Forecast (0.5, 0.3, 0.2), home win: cumulative (0.5, 0.8) vs (1, 1)
    # -> ((0.5)^2 + (0.2)^2) / 2 = 0.145
    assert rps(np.array([[0.5, 0.3, 0.2]]), ["H"]) == pytest.approx(0.145)


def test_rps_rewards_being_close_in_order():
    # Home win happened: a draw-leaning forecast should beat an away-leaning one
    draw_leaning = np.array([[0.2, 0.6, 0.2]])
    away_leaning = np.array([[0.2, 0.2, 0.6]])
    assert rps(draw_leaning, ["H"]) < rps(away_leaning, ["H"])


def test_log_loss_and_brier_hand_calculation():
    probs = np.array([[0.5, 0.3, 0.2]])
    assert log_loss(probs, ["D"]) == pytest.approx(-np.log(0.3))
    assert brier(probs, ["D"]) == pytest.approx(0.25 + 0.49 + 0.04)


def test_compare_with_market_scores_the_same_matches():
    matches = pd.DataFrame({
        "match_id": ["a", "b", "c"], "season": [2020, 2020, 2021], "result": ["H", "A", "D"],
        "pin_close_h": [2.0, 3.0, np.nan], "pin_close_d": [3.5, 3.4, np.nan], "pin_close_a": [4.0, 2.4, np.nan],
    })  # fmt: skip
    preds = pd.DataFrame({"match_id": ["a", "b", "c"], "p_home": [0.5] * 3, "p_draw": [0.3] * 3, "p_away": [0.2] * 3})
    table = compare_with_market(preds, matches, "Model", markets={"Pinnacle": "pin_close"})
    overall = table[table["season"] == "All"].set_index("forecaster")
    assert overall.loc["Model", "matches"] == 2  # match c has no Pinnacle odds, so it is left out for both
    assert overall.loc["Pinnacle", "matches"] == 2


def test_base_rate_forecast_uses_only_earlier_seasons():
    matches = pd.DataFrame({"season": [1, 1, 1, 1, 2, 2], "result": ["H", "H", "D", "A", "A", "A"]})
    target = matches[matches["season"] == 2]
    probs = base_rate_forecast(matches, target)
    assert np.allclose(probs, [[0.5, 0.25, 0.25]] * 2)  # season 2's own results are not used
