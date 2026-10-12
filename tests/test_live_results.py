"""Tests for the faster football-data.org results."""

import pandas as pd
import pytest

from pipeline import live_results

TEAMS = {"FC Internazionale Milano": "Inter", "Parma Calcio 1913": "Parma", "AS Roma": "Roma", "SS Lazio": "Lazio",
         "Inter": "Inter", "Roma": "Roma"}  # fmt: skip


def api_match(home, away, hg, ag, utc="2026-10-10T16:00:00Z", status="FINISHED"):
    return {"utcDate": utc, "status": status, "homeTeam": {"name": home, "shortName": home.split()[-1]},
            "awayTeam": {"name": away, "shortName": away.split()[-1]},
            "score": {"fullTime": {"home": hg, "away": ag}}}  # fmt: skip


def main_source() -> pd.DataFrame:
    """Two matches football-data.co.uk already has."""
    return pd.DataFrame({
        "match_id": ["2026-09-19_Roma_Inter", "2026-09-19_Lazio_Parma"], "season": [2026, 2026],
        "date": pd.to_datetime(["2026-09-19", "2026-09-19"]), "time": ["20:45", "18:00"],
        "home_team": ["Roma", "Lazio"], "away_team": ["Inter", "Parma"],
        "home_goals": [2, 1], "away_goals": [2, 0], "result": ["D", "H"],
    })  # fmt: skip


def test_parse_reads_scores_and_converts_kickoff_to_italian_time():
    payload = {"matches": [api_match("FC Internazionale Milano", "Parma Calcio 1913", 0, 1, utc="2026-10-10T16:00:00Z"),
                           api_match("AS Roma", "SS Lazio", None, None, status="SCHEDULED")]}  # fmt: skip
    live = live_results.parse(payload, 2026, TEAMS)
    assert len(live) == 1  # the unplayed match is ignored
    row = live.iloc[0]
    assert (row["home_team"], row["away_team"], row["home_goals"], row["away_goals"], row["result"]) == ("Inter", "Parma", 0, 1, "A")
    assert row["time"] == "18:00"  # 16:00 UTC = 18:00 in Italy in October


def test_unknown_team_names_are_skipped_not_fatal():
    live = live_results.parse({"matches": [api_match("Nowhere FC", "AS Roma", 1, 0)]}, 2026, TEAMS)
    assert live.empty


def test_missing_matches_are_added_with_blank_odds_and_stats():
    live = live_results.parse({"matches": [api_match("FC Internazionale Milano", "Parma Calcio 1913", 0, 1)]}, 2026, TEAMS)
    combined, added = live_results.fill_gaps(main_source(), live)
    assert added == 1 and len(combined) == 3
    new = combined[combined["source"] == live_results.SOURCE_LIVE].iloc[0]
    assert new["match_id"] == "2026-10-10_Inter_Parma"
    assert pd.isna(new["avg_close_h"]) and pd.isna(new["home_corners"])  # filled in later by football-data.co.uk
    assert (combined["source"] == live_results.SOURCE_MAIN).sum() == 2


def test_matches_the_main_source_already_has_are_not_duplicated():
    live = live_results.parse({"matches": [api_match("AS Roma", "FC Internazionale Milano", 2, 2, utc="2026-09-19T18:45:00Z")]}, 2026, TEAMS)
    combined, added = live_results.fill_gaps(main_source(), live)
    assert added == 0 and len(combined) == 2


def test_disagreeing_scores_stop_the_update():
    live = live_results.parse({"matches": [api_match("AS Roma", "FC Internazionale Milano", 3, 2)]}, 2026, TEAMS)
    with pytest.raises(ValueError, match="disagree"):
        live_results.fill_gaps(main_source(), live)
