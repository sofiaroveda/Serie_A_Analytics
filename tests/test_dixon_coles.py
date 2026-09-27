"""Tests for the Dixon-Coles model."""

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import approx_fprime

from pipeline import dixon_coles as dc
from pipeline.dixon_coles import DCParams
from tests.conftest import assert_no_lookahead


def test_score_matrix_is_a_probability_distribution():
    matrix = dc.score_matrix(1.5, 1.1, rho=-0.1)
    assert matrix.shape == (dc.MAX_GOALS + 1, dc.MAX_GOALS + 1)
    assert matrix.sum() == pytest.approx(1) and (matrix >= 0).all()


def test_negative_rho_adds_draws_at_0_0_and_1_1():
    plain, corrected = dc.score_matrix(1.3, 1.0, rho=0.0), dc.score_matrix(1.3, 1.0, rho=-0.1)
    assert corrected[0, 0] > plain[0, 0] and corrected[1, 1] > plain[1, 1]
    assert corrected[1, 0] < plain[1, 0] and corrected[0, 1] < plain[0, 1]


def test_outcome_probabilities_hand_check():
    matrix = np.zeros((4, 4))
    matrix[2, 1], matrix[1, 1], matrix[0, 3] = 0.5, 0.3, 0.2  # 2-1, 1-1, 0-3
    p = dc.outcome_probabilities(matrix)
    assert (p["p_home"], p["p_draw"], p["p_away"]) == pytest.approx((0.5, 0.3, 0.2))
    assert p["p_over_2_5"] == pytest.approx(0.7)  # 2-1 and 0-3 have 3 goals
    assert p["p_btts"] == pytest.approx(0.8)  # 2-1 and 1-1


def test_gradient_matches_numerical_derivative():
    rng = np.random.default_rng(0)
    n, m = 6, 200
    home, away = rng.integers(0, n, m), rng.integers(0, n, m)
    x, y, w = rng.poisson(1.4, m), rng.poisson(1.1, m), rng.uniform(0.2, 1, m)
    prior_att, prior_def = rng.normal(0, 0.1, n), rng.normal(0, 0.1, n)
    theta = np.concatenate([rng.normal(0, 0.2, 2 * n), [0.3, 0.2, -0.08]])

    def f(t):
        return dc._negative_log_likelihood(t, home, away, x, y, w, prior_att, prior_def, 2.0)[0]

    analytic = dc._negative_log_likelihood(theta, home, away, x, y, w, prior_att, prior_def, 2.0)[1]
    np.testing.assert_allclose(analytic, approx_fprime(theta, f, 1e-7), rtol=1e-4, atol=1e-3)


def test_fit_recovers_known_strengths():
    rng = np.random.default_rng(1)
    teams = ["A", "B", "C", "D"]
    attack = {"A": 0.4, "B": 0.1, "C": -0.1, "D": -0.4}
    defence = {"A": -0.3, "B": 0.0, "C": 0.1, "D": 0.2}
    rows = []
    for k in range(3000):
        h, a = rng.choice(teams, 2, replace=False)
        rows.append({"home_team": h, "away_team": a, "date": pd.Timestamp("2020-01-01"),
                     "home_goals": rng.poisson(np.exp(0.1 + 0.3 + attack[h] + defence[a])),
                     "away_goals": rng.poisson(np.exp(0.1 + attack[a] + defence[h]))})  # fmt: skip
    model = dc.fit(pd.DataFrame(rows), pd.Timestamp("2020-01-02"), DCParams(ridge=0.0))
    fitted = dict(zip(model.teams, model.attack))
    true_centred = {t: v - np.mean(list(attack.values())) for t, v in attack.items()}
    for team in teams:
        assert fitted[team] == pytest.approx(true_centred[team], abs=0.07)
    assert model.home_advantage == pytest.approx(0.3, abs=0.07)


def test_dixon_coles_predictions_never_use_results_on_or_after_match_date(league):
    def predict(matches):
        return dc.predict_matches(matches, DCParams(), first_season=1)

    dates = sorted(league.loc[league["season"] >= 1, "date"].unique())
    cuts = [pd.Timestamp(d) for d in (dates[0], dates[7], dates[len(dates) // 2], dates[-1])]
    assert_no_lookahead(predict, league, cuts)


def test_predict_fixtures_gives_valid_probabilities(league):
    played = league[league["season"] <= 2]
    upcoming = league[league["season"] == 3].head(3)
    preds = dc.predict_fixtures(played, upcoming, DCParams(), season=3)
    assert np.allclose(preds[["p_home", "p_draw", "p_away"]].sum(axis=1), 1)
    assert preds["exp_home_goals"].gt(0).all()
