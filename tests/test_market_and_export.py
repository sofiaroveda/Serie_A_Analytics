"""Tests for odds -> probabilities and the site data export."""

import numpy as np
import pandas as pd
import pytest

from pipeline.export import build_site_data, league_table, upcoming_from_schedule
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


EMPTY_FIXTURES = pd.DataFrame(columns=["match_id", "date", "time", "home_team", "away_team", "avg_h", "avg_d", "avg_a"])


def make_schedule() -> pd.DataFrame:
    """Matches a-c from make_matches (matchdays 1-2) plus one unplayed match on matchday 3."""
    return pd.DataFrame({
        "season": [2026] * 4, "matchday": [1, 1, 2, 3],
        "date": pd.to_datetime(["2026-08-22", "2026-08-22", "2026-08-29", "2026-09-05"]),
        "time": ["18:00", "20:45", "20:45", "15:00"],
        "home_team": ["Inter", "Roma", "Milan", "Lazio"], "away_team": ["Milan", "Lazio", "Roma", "Inter"],
        "home_goals": pd.array([2, 1, 0, None], dtype="Int64"), "away_goals": pd.array([0, 1, 0, None], dtype="Int64"),
    })  # fmt: skip


def test_build_site_data_lists_every_scheduled_match_with_its_matchday():
    site = build_site_data(make_matches(), EMPTY_FIXTURES, make_schedule())
    by_id = {m["match_id"]: m for m in site["matches"]}
    assert len(site["matches"]) == 4
    assert by_id["c"]["matchday"] == 2 and by_id["c"]["status"] == "played"
    upcoming = [m for m in site["matches"] if m["status"] == "upcoming"]
    assert len(upcoming) == 1 and upcoming[0]["matchday"] == 3 and upcoming[0]["home_goals"] is None
    assert site["summary"]["current_matchday"] == 3
    assert site["summary"]["season"] == "2026/27"
    # favourite won match a (home), lost b (draw, favourite away), lost c (draw, favourite home)
    assert site["summary"]["favourite_win_rate"] == pytest.approx(1 / 3, abs=1e-4)


def test_upcoming_match_gets_market_odds_when_published():
    fixtures = pd.DataFrame({
        "match_id": ["x"], "date": pd.to_datetime(["2026-09-05"]), "time": ["15:00"],
        "home_team": ["Lazio"], "away_team": ["Inter"], "avg_h": [3.0], "avg_d": [3.4], "avg_a": [2.3],
    })  # fmt: skip
    site = build_site_data(make_matches(), fixtures, make_schedule())
    upcoming = next(m for m in site["matches"] if m["status"] == "upcoming")
    assert upcoming["odds_source"] == "Market average" and upcoming["p_home"] < upcoming["p_away"]


def test_upcoming_from_schedule_excludes_played_matches():
    upcoming = upcoming_from_schedule(make_schedule(), make_matches())
    assert list(upcoming["home_team"]) == ["Lazio"] and upcoming["match_id"].iloc[0] == "2026-09-05_Lazio_Inter"


def test_build_site_data_attaches_model_and_scoreboard():
    elo = pd.DataFrame({"match_id": ["a", "b", "c"], "p_home": [0.5] * 3, "p_draw": [0.3] * 3, "p_away": [0.2] * 3})
    site = build_site_data(make_matches(), EMPTY_FIXTURES, make_schedule(), {"elo": elo})
    assert next(m for m in site["matches"] if m["match_id"] == "a")["elo_home"] == 0.5
    board = site["summary"]["scoreboard"]
    assert board["matches"] == 3 and 0 < board["elo_rps"] < 1 and 0 < board["market_rps"] < 1


def test_build_site_data_without_model_has_null_probabilities():
    site = build_site_data(make_matches(), EMPTY_FIXTURES, make_schedule())
    assert all(m["elo_home"] is None for m in site["matches"])
    assert site["summary"]["scoreboard"] is None


def test_goals_stay_whole_numbers_in_the_output():
    site = build_site_data(make_matches(), EMPTY_FIXTURES, make_schedule())
    played = next(m for m in site["matches"] if m["match_id"] == "a")
    assert played["home_goals"] == 2 and isinstance(played["home_goals"], int)
    assert all(isinstance(row["goals_for"], int) for row in site["table"])
