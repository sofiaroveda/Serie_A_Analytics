"""Tests for the season simulation."""

import numpy as np
import pandas as pd
import pytest

from pipeline.dixon_coles import score_matrix
from pipeline.simulate import simulate_season

TEAMS = ["A", "B", "C", "D", "E", "F"]


def fixtures(strength: dict[str, float]) -> pd.DataFrame:
    """Every pair meets twice; stronger teams have higher expected goals."""
    rows = [{"home_team": h, "away_team": a,
             "exp_home_goals": 1.4 * np.exp(strength[h] - strength[a]),
             "exp_away_goals": 1.1 * np.exp(strength[a] - strength[h])}
            for h in TEAMS for a in TEAMS if h != a]  # fmt: skip
    return pd.DataFrame(rows)


EVEN = {t: 0.0 for t in TEAMS}


def test_more_uncertainty_spreads_the_chances():
    strength = {"A": 0.6, "B": 0.3, "C": 0.1, "D": -0.1, "E": -0.3, "F": -0.6}
    empty = pd.DataFrame(columns=["home_team", "away_team", "home_goals", "away_goals"])
    sure = simulate_season(empty, fixtures(strength), n_sims=4000, strength_sd=0.0).set_index("team")
    unsure = simulate_season(empty, fixtures(strength), n_sims=4000, strength_sd=0.3).set_index("team")
    assert unsure.loc["A", "p_title"] < sure.loc["A", "p_title"]
    assert unsure.loc["F", "p_title"] > sure.loc["F", "p_title"]


def test_expected_points_match_the_goal_rates():
    # Two equal teams, no uncertainty: each side's expected points per game = 3 P(win) + P(draw)
    matches = pd.DataFrame({"home_team": ["A"] * 400, "away_team": ["B"] * 400, "exp_home_goals": 1.3, "exp_away_goals": 1.3})
    table = simulate_season(pd.DataFrame(columns=["home_team", "away_team", "home_goals", "away_goals"]),
                            matches, n_sims=500, strength_sd=0.0).set_index("team")  # fmt: skip
    m = score_matrix(1.3, 1.3, 0.0)
    per_game = 3 * np.tril(m, -1).sum() + np.trace(m)
    assert table.loc["A", "exp_points"] / 400 == pytest.approx(per_game, rel=0.01)


def test_probabilities_are_consistent():
    table = simulate_season(pd.DataFrame(columns=["home_team", "away_team", "home_goals", "away_goals"]),
                            fixtures(EVEN), n_sims=2000)  # fmt: skip
    assert table["p_title"].sum() == pytest.approx(1)
    assert table["p_top4"].sum() == pytest.approx(4)
    assert table["p_relegation"].sum() == pytest.approx(3)
    positions = np.stack(table["position_probs"])
    assert np.allclose(positions.sum(axis=1), 1) and np.allclose(positions.sum(axis=0), 1)


def test_stronger_teams_finish_higher():
    strength = {"A": 0.6, "B": 0.3, "C": 0.1, "D": -0.1, "E": -0.3, "F": -0.6}
    table = simulate_season(pd.DataFrame(columns=["home_team", "away_team", "home_goals", "away_goals"]),
                            fixtures(strength), n_sims=3000).set_index("team")  # fmt: skip
    assert table.loc["A", "p_title"] > table.loc["B", "p_title"] > table.loc["F", "p_title"]
    assert table.loc["F", "p_relegation"] > table.loc["A", "p_relegation"]
    assert list(table.index[:2]) == ["A", "B"]


def test_finished_season_is_certain():
    rng = np.random.default_rng(0)
    played = fixtures(EVEN)[["home_team", "away_team"]].copy()
    played["home_goals"] = rng.integers(0, 4, len(played))
    played["away_goals"] = rng.integers(0, 4, len(played))
    remaining = fixtures(EVEN).iloc[0:0]
    table = simulate_season(played, remaining, n_sims=500)
    # Nothing left to play: every team's final position is known (up to exact ties)
    assert table["p_title"].max() == 1.0
    assert (table["exp_points"] == table["points"]).all()
    assert table["played"].sum() == 2 * len(played)


def test_current_points_are_kept():
    played = pd.DataFrame({"home_team": ["A"], "away_team": ["B"], "home_goals": [2], "away_goals": [0]})
    remaining = fixtures(EVEN).query("not (home_team == 'A' and away_team == 'B')")
    table = simulate_season(played, remaining, n_sims=500).set_index("team")
    assert table.loc["A", "points"] == 3 and table.loc["B", "points"] == 0
    assert table.loc["A", "exp_points"] > table.loc["B", "exp_points"]
