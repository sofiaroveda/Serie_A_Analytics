"""Tests for the Elo model."""

import numpy as np
import pandas as pd
import pytest

from pipeline import elo
from pipeline.elo import EloParams
from tests.conftest import assert_no_lookahead


def test_expected_score_is_half_for_equal_teams_on_neutral_ground():
    assert elo.expected_home_score(1500, 1500, home_advantage=0) == pytest.approx(0.5)


def test_expected_score_400_points_is_ten_to_one():
    # Elo's definition: a 400-point gap means odds of 10 to 1
    assert elo.expected_home_score(1900, 1500, home_advantage=0) == pytest.approx(10 / 11)


def test_goal_diff_multiplier():
    assert elo.goal_diff_multiplier(1) == 1.0
    assert elo.goal_diff_multiplier(-1) == 1.0
    assert elo.goal_diff_multiplier(0) == 1.0
    assert elo.goal_diff_multiplier(2) == 1.5
    assert elo.goal_diff_multiplier(3) == pytest.approx(14 / 8)


def test_new_season_regresses_and_places_promoted_teams_below_average():
    params = EloParams(season_regression=0.5, promoted_gap=100)
    old = {"Strong": 1700.0, "Weak": 1300.0, "Relegated": 1400.0}
    new = elo.start_new_season(old, {"Strong", "Weak", "Promoted"}, params)
    assert set(new) == {"Strong", "Weak", "Promoted"}
    assert np.mean(list(new.values())) == pytest.approx(elo.MEAN_RATING)
    assert new["Strong"] - new["Weak"] == pytest.approx(200)  # 400-point gap halved
    assert new["Promoted"] < elo.MEAN_RATING


def test_ratings_are_zero_sum_and_winner_gains(league):
    _, end_of_first = elo.run_elo(league[league["season"] == 0], EloParams())
    assert np.mean(list(end_of_first.values())) == pytest.approx(elo.MEAN_RATING)

    one = league.iloc[[0]].copy()
    one.loc[:, ["home_goals", "away_goals", "result"]] = [2, 0, "H"]
    _, after = elo.run_elo(one, EloParams())
    home, away = one["home_team"].iloc[0], one["away_team"].iloc[0]
    assert after[home] > elo.MEAN_RATING > after[away]


def test_same_day_matches_use_ratings_from_before_that_day():
    # Team A plays twice on the same date (artificial): the second match must not see the first's result
    matches = pd.DataFrame({
        "match_id": ["1", "2"], "season": [0, 0], "date": pd.to_datetime(["2000-01-01"] * 2),
        "home_team": ["A", "A"], "away_team": ["B", "C"],
        "home_goals": [5, 0], "away_goals": [0, 0], "result": ["H", "D"],
    })  # fmt: skip
    history, _ = elo.run_elo(matches, EloParams())
    assert history["elo_home"].tolist() == [1500.0, 1500.0]


def test_outcome_model_probabilities_are_valid_and_monotonic():
    model = elo.OutcomeModel(slope=2.0, draw_low=-1.0, draw_high=0.3)
    probs = model.probabilities(np.array([-400, 0, 400]))
    assert np.allclose(probs.sum(axis=1), 1) and (probs > 0).all()
    assert probs[2, 0] > probs[1, 0] > probs[0, 0]  # home win more likely as the gap grows
    assert probs[0, 2] > probs[1, 2] > probs[2, 2]


def test_fit_outcome_model_recovers_known_parameters():
    rng = np.random.default_rng(0)
    true = elo.OutcomeModel(slope=2.5, draw_low=-0.8, draw_high=0.5)
    gap = rng.normal(60, 150, 20_000)
    probs = true.probabilities(gap)
    results = np.array(["H", "D", "A"])[[rng.choice(3, p=p) for p in probs]]
    fitted = elo.fit_outcome_model(gap, results)
    assert fitted.slope == pytest.approx(true.slope, abs=0.2)
    assert fitted.draw_low == pytest.approx(true.draw_low, abs=0.1)
    assert fitted.draw_high == pytest.approx(true.draw_high, abs=0.1)


def test_elo_predictions_never_use_results_on_or_after_match_date(league):
    def predict(matches):
        return elo.predict_matches(matches, EloParams(), first_season=1)

    dates = sorted(league.loc[league["season"] >= 1, "date"].unique())
    cuts = [pd.Timestamp(d) for d in (dates[0], dates[5], dates[len(dates) // 2], dates[-1])]
    assert_no_lookahead(predict, league, cuts)


def test_predict_fixtures_uses_latest_ratings(league):
    played = league[league["season"] <= 2]
    upcoming = league[league["season"] == 3].head(2)
    preds = elo.predict_fixtures(played, upcoming, EloParams(), season=3)
    assert np.allclose(preds[["p_home", "p_draw", "p_away"]].sum(axis=1), 1)
    assert preds[["elo_home", "elo_away"]].notna().all().all()
