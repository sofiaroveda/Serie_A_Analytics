"""Tests for odds -> probabilities and the site data export."""

import numpy as np
import pandas as pd
import pytest

from pipeline.export import build_site_data, league_table
from pipeline.market import best_available_probabilities, implied_probabilities, overround


def test_implied_probabilities_remove_the_margin():
    odds = pd.DataFrame({"h": [2.0], "d": [3.4], "a": [4.0]})
    probs = implied_probabilities(odds).iloc[0]
    raw = np.array([1 / 2.0, 1 / 3.4, 1 / 4.0])
    assert probs.sum() == pytest.approx(1.0)
    assert list(probs) == pytest.approx(list(raw / raw.sum()))
    assert overround(odds).iloc[0] == pytest.approx(raw.sum() - 1)


def test_fair_odds_have_no_margin():
    odds = pd.DataFrame({"h": [2.0], "d": [4.0], "a": [4.0]})  # 0.5 + 0.25 + 0.25 = 1
    assert overround(odds).iloc[0] == pytest.approx(0.0)
    assert list(implied_probabilities(odds).iloc[0]) == pytest.approx([0.5, 0.25, 0.25])


def test_best_available_falls_back_to_next_source():
    matches = pd.DataFrame({
        "pin_close_h": [2.0, np.nan], "pin_close_d": [3.4, np.nan], "pin_close_a": [4.0, np.nan],
        "avg_close_h": [2.1, 1.5], "avg_close_d": [3.3, 4.0], "avg_close_a": [3.9, 7.0],
    })  # fmt: skip
    probs, source = best_available_probabilities(matches, ["pin_close", "avg_close"])
    assert list(source) == ["pin_close", "avg_close"]
    assert probs.sum(axis=1).tolist() == pytest.approx([1.0, 1.0])


def make_matches() -> pd.DataFrame:
    return pd.DataFrame({
        "match_id": ["a", "b", "c"],
        "season": [2026, 2026, 2026],
        "date": pd.to_datetime(["2026-08-22", "2026-08-22", "2026-08-29"]),
        "time": ["18:00", "20:45", "20:45"],
        "home_team": ["Inter", "Roma", "Milan"],
        "away_team": ["Milan", "Lazio", "Roma"],
        "home_goals": [2, 1, 0],
        "away_goals": [0, 1, 0],
        "result": ["H", "D", "D"],
        "avg_close_h": [1.8, 2.5, 2.2], "avg_close_d": [3.6, 3.2, 3.3], "avg_close_a": [4.5, 3.0, 3.4],
    })  # fmt: skip


def test_league_table_points_and_order():
    table = league_table(make_matches()).set_index("team")
    assert table.loc["Inter", "points"] == 3 and table.loc["Inter", "position"] == 1
    assert table.loc["Roma", "points"] == 2 and table.loc["Roma", "played"] == 2
    assert table.loc["Milan", "goal_diff"] == -2 and table.loc["Milan", "position"] == 4
    assert table["position"].tolist() == [1, 2, 3, 4]


def test_build_site_data_handles_no_fixtures():
    fixtures = pd.DataFrame(columns=["match_id", "date", "time", "home_team", "away_team", "avg_h", "avg_d", "avg_a"])
    site = build_site_data(make_matches(), fixtures)
    assert site["fixtures"] == []
    assert site["summary"]["season"] == "2026/27"
    assert site["results"][0]["match_id"] == "c"  # newest first
    assert site["results"][0]["odds_source"] == "Market average closing"
    # favourite won match a (home), lost b (draw, favourite away), lost c (draw, favourite home)
    assert site["summary"]["favourite_win_rate"] == pytest.approx(1 / 3, abs=1e-4)


def test_build_site_data_attaches_model_and_scoreboard():
    fixtures = pd.DataFrame(columns=["match_id", "date", "time", "home_team", "away_team", "avg_h", "avg_d", "avg_a"])
    elo = pd.DataFrame({"match_id": ["a", "b", "c"], "p_home": [0.5] * 3, "p_draw": [0.3] * 3, "p_away": [0.2] * 3})
    site = build_site_data(make_matches(), fixtures, elo_results=elo)
    assert site["results"][0]["elo_home"] == 0.5
    board = site["summary"]["scoreboard"]
    assert board["matches"] == 3 and 0 < board["elo_rps"] < 1 and 0 < board["market_rps"] < 1


def test_build_site_data_without_model_has_null_probabilities():
    fixtures = pd.DataFrame(columns=["match_id", "date", "time", "home_team", "away_team", "avg_h", "avg_d", "avg_a"])
    site = build_site_data(make_matches(), fixtures)
    assert site["results"][0]["elo_home"] is None
    assert site["summary"]["scoreboard"] is None
