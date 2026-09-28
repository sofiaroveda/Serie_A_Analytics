"""Tests for downloading helpers and cleaning. All offline: no network calls."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import data

TEAM_MAP = {"Inter": "Inter", "Milan": "Milan", "AC Milan": "Milan", "Roma": "Roma"}


def old_format_raw() -> pd.DataFrame:
    """Mimics a 2000s file: 2-digit years, no Time column, Betbrain average odds."""
    return pd.DataFrame(
        {
            "Div": ["I1", "I1"],
            "Date": ["27/08/05", "28/08/05"],
            "HomeTeam": ["Inter", "Roma"],
            "AwayTeam": ["Milan", "Inter"],
            "FTHG": [2, 0],
            "FTAG": [1, 0],
            "FTR": ["H", "D"],
            "B365H": [2.0, 2.5],
            "B365D": [3.2, 3.1],
            "B365A": [3.8, 2.9],
            "BbAvH": [1.95, 2.45],
            "BbAvD": [3.1, 3.0],
            "BbAvA": [3.7, 2.8],
        }
    )


def new_format_raw() -> pd.DataFrame:
    """Mimics a recent file: 4-digit years, Time column, Pinnacle and closing odds."""
    return pd.DataFrame(
        {
            "Div": ["I1"],
            "Date": ["17/08/2024"],
            "Time": ["20:45"],
            "HomeTeam": ["AC Milan"],
            "AwayTeam": ["Roma"],
            "FTHG": [1],
            "FTAG": [3],
            "FTR": ["A"],
            "PSH": [2.1], "PSD": [3.4], "PSA": [3.6],
            "PSCH": [2.0], "PSCD": [3.5], "PSCA": [3.8],
            "AvgH": [2.05], "AvgD": [3.3], "AvgA": [3.5],
        }
    )  # fmt: skip


def test_season_code():
    assert data.season_code(2005) == "0506"
    assert data.season_code(2024) == "2425"
    assert data.season_code(2099) == "9900"


def test_current_season_rolls_over_in_july():
    assert data.current_season_start(date(2026, 6, 30)) == 2025
    assert data.current_season_start(date(2026, 7, 1)) == 2026


def test_season_starts_runs_from_2005_to_current():
    starts = data.season_starts(today=date(2026, 9, 27))
    assert starts[0] == 2005 and starts[-1] == 2026 and len(starts) == 22


def test_season_url():
    assert data.season_url(2024) == "https://www.football-data.co.uk/mmz4281/2425/I1.csv"


def test_parse_dates_handles_both_year_formats():
    parsed = data.parse_dates(pd.Series(["27/08/05", "17/08/2024"]))
    assert list(parsed.dt.date) == [date(2005, 8, 27), date(2024, 8, 17)]


def test_unknown_team_name_fails_loudly():
    with pytest.raises(ValueError, match="Nowhere FC"):
        data.standardise_team_names(pd.Series(["Inter", "Nowhere FC"]), TEAM_MAP)


def test_aliases_map_to_one_canonical_name():
    names = data.standardise_team_names(pd.Series([" AC Milan", "Milan"]), TEAM_MAP)
    assert list(names) == ["Milan", "Milan"]


def test_clean_old_format():
    matches = data.clean_season(old_format_raw(), 2005, TEAM_MAP)
    assert list(matches["home_team"]) == ["Inter", "Roma"]
    assert matches["season"].eq(2005).all()
    assert matches.loc[0, "avg_h"] == 1.95  # taken from BbAvH
    assert matches[["pin_h", "pin_close_h", "avg_close_h"]].isna().all().all()  # not in old files
    assert matches.loc[0, "match_id"] == "2005-08-27_Inter_Milan"


def test_clean_new_format():
    matches = data.clean_season(new_format_raw(), 2024, TEAM_MAP)
    row = matches.iloc[0]
    assert row["home_team"] == "Milan" and row["time"] == "20:45"
    assert (row["pin_close_h"], row["pin_close_d"], row["pin_close_a"]) == (2.0, 3.5, 3.8)
    assert row["avg_h"] == 2.05
    assert np.isnan(row["b365_h"])  # column absent from this file


def test_result_inconsistent_with_score_is_rejected():
    raw = old_format_raw()
    raw.loc[0, "FTR"] = "A"  # Inter won 2-1, so "A" is wrong
    with pytest.raises(ValueError, match="Result does not match"):
        data.clean_season(raw, 2005, TEAM_MAP)


def test_impossible_odds_are_rejected():
    raw = old_format_raw()
    raw.loc[0, "B365H"] = 0.9
    with pytest.raises(ValueError, match="odds"):
        data.clean_season(raw, 2005, TEAM_MAP)


def test_clean_fixtures_filters_to_serie_a_and_allows_empty():
    raw = pd.concat([new_format_raw(), new_format_raw().assign(Div="E0", HomeTeam="Arsenal")])
    fixtures = data.clean_fixtures(raw, TEAM_MAP)
    assert list(fixtures["home_team"]) == ["Milan"]

    empty = data.clean_fixtures(raw[raw["Div"] == "E0"], TEAM_MAP)
    assert empty.empty and "pin_h" in empty


def test_load_raw_csv_strips_byte_order_mark_and_blank_rows(tmp_path: Path):
    path = tmp_path / "I1.csv"
    path.write_bytes("﻿Div,Date,HomeTeam\nI1,17/08/2024,Inter\n,,\n".encode("utf-8"))
    raw = data.load_raw_csv(path)
    assert list(raw.columns) == ["Div", "Date", "HomeTeam"] and len(raw) == 1


def test_team_names_file_has_no_conflicting_aliases():
    table = pd.read_csv(data.TEAM_NAMES_PATH)
    assert not table["alias"].duplicated().any()
    assert set(table["team"]) <= set(table["alias"])  # every canonical name maps to itself


def openfootball_raw() -> dict:
    return {"matches": [
        {"round": "Matchday 1", "date": "2026-08-22", "time": "18:30", "team1": "FC Internazionale Milano",
         "team2": "AC Milan", "score": {"ht": [1, 0], "ft": [2, 1]}},
        {"round": "Matchday 1", "date": "2026-08-22", "time": "20:45", "team1": "AS Roma", "team2": "SS Lazio",
         "score": {"ft": [0, 0]}},
        {"round": "Matchday 2", "date": "2026-08-29", "time": "20:45", "team1": "SS Lazio", "team2": "Inter"},
    ]}  # fmt: skip


SCHEDULE_TEAM_MAP = {**TEAM_MAP, "FC Internazionale Milano": "Inter", "AS Roma": "Roma", "SS Lazio": "Lazio"}


def test_clean_schedule_reads_matchdays_and_unplayed_matches():
    schedule = data.clean_schedule(openfootball_raw(), 2026, SCHEDULE_TEAM_MAP)
    assert list(schedule["matchday"]) == [1, 1, 2]
    assert list(schedule["home_team"]) == ["Inter", "Roma", "Lazio"]
    assert schedule.loc[0, "home_goals"] == 2 and pd.isna(schedule.loc[2, "home_goals"])


def test_schedule_with_a_team_twice_in_a_matchday_is_rejected():
    raw = openfootball_raw()
    raw["matches"][2]["round"] = "Matchday 1"  # Lazio would play twice on matchday 1
    with pytest.raises(ValueError, match="twice in the same matchday"):
        data.clean_schedule(raw, 2026, SCHEDULE_TEAM_MAP)


def test_schedule_cross_check_with_results():
    schedule = data.clean_schedule(openfootball_raw(), 2026, SCHEDULE_TEAM_MAP)
    results = pd.DataFrame({"match_id": ["m1"], "season": [2026], "home_team": ["Inter"], "away_team": ["Milan"],
                            "home_goals": [2], "away_goals": [1]})  # fmt: skip
    data.check_schedule_matches_results(schedule, results)  # agrees: no error

    with pytest.raises(ValueError, match="disagree"):
        data.check_schedule_matches_results(schedule, results.assign(away_goals=3))
    with pytest.raises(ValueError, match="not found"):
        data.check_schedule_matches_results(schedule, results.assign(home_team="Juventus"))


def test_match_stats_are_kept_and_missing_ones_are_blank():
    raw = new_format_raw().assign(HS=[14], AS=[9], HST=[5], AST=[4], HC=[6], AC=[2], HF=[11], AF=[13],
                                  HY=[2], AY=[3], HR=[0], AR=[1])  # fmt: skip
    row = data.clean_season(raw, 2024, TEAM_MAP).iloc[0]
    assert (row["home_shots"], row["away_on_target"], row["away_red"]) == (14, 4, 1)
    assert np.isnan(row["home_xg"])  # xG only exists from 2026/27
