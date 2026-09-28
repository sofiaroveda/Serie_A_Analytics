"""Tests for the corners / cards / shots models."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import poisson

from pipeline import stats_model
from tests.conftest import assert_no_lookahead


def with_corners(league: pd.DataFrame, seed: int = 3) -> pd.DataFrame:
    """The made-up league with corners: stronger teams (lower index) win more of them."""
    rng = np.random.default_rng(seed)
    order = {t: i for i, t in enumerate(["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta"])}
    out = league.copy()
    out["home_corners"] = [rng.poisson(6.5 - 0.3 * order[h] + 0.2 * order[a]) for h, a in zip(out.home_team, out.away_team)]
    out["away_corners"] = [rng.poisson(5.0 - 0.3 * order[a] + 0.2 * order[h]) for h, a in zip(out.home_team, out.away_team)]
    return out


def test_p_over_matches_poisson_without_extra_spread():
    assert stats_model.p_over(10.0, 9.5, None) == pytest.approx(poisson.sf(9, 10.0))


def test_extra_spread_makes_extreme_totals_more_likely():
    # With a negative binomial, very high totals are more likely than under a Poisson with the same mean
    assert stats_model.p_over(10.0, 15.5, 8.0) > stats_model.p_over(10.0, 15.5, None)


def test_counts_are_read_from_the_stat_columns():
    matches = pd.DataFrame({"home_goals": [1], "away_goals": [0], "home_corners": [7], "away_corners": [3]})
    counts = stats_model.as_counts(matches, "corners")
    assert (counts["home_goals"].iloc[0], counts["away_goals"].iloc[0]) == (7, 3)


def test_stronger_teams_are_expected_to_win_more_corners(league):
    data = with_corners(league)
    preds = stats_model.predict_matches(data, "corners", first_season=3).merge(data[["match_id", "home_team", "away_team"]])
    alpha_home = preds[preds.home_team == "Alpha"]["exp_home"].mean()
    theta_home = preds[preds.home_team == "Theta"]["exp_home"].mean()
    assert alpha_home > theta_home


def test_stat_predictions_never_use_results_on_or_after_match_date(league):
    data = with_corners(league)

    def predict(matches):
        # scramble_from changes goals; make corners follow the scrambled goals so the test has teeth
        m = matches.assign(home_corners=matches["home_goals"] * 2 + 3, away_corners=matches["away_goals"] * 2 + 2)
        preds = stats_model.predict_matches(m, "corners", first_season=1).merge(m[["match_id", "date"]])
        # the check reads p_home/p_draw/p_away: reuse those names for the three numbers we predict
        return preds.assign(p_home=preds["exp_home"], p_draw=preds["exp_away"], p_away=preds["exp_home"] + preds["exp_away"])

    dates = sorted(data.loc[data["season"] >= 1, "date"].unique())
    assert_no_lookahead(predict, data, [pd.Timestamp(d) for d in (dates[3], dates[len(dates) // 2])])
