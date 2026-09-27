"""Tests for the append-only prediction record."""

import json
from datetime import datetime, timezone

import pandas as pd

from pipeline.ledger import kickoff_times, ledger_path, next_round, record_forecasts

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def forecasts(p_home: float = 0.5) -> pd.DataFrame:
    return pd.DataFrame({
        "match_id": ["m1", "m2"], "matchday": [6, 6],
        "date": pd.to_datetime(["2026-10-10", "2026-10-11"]), "time": ["15:00", "20:45"],
        "home_team": ["Genoa", "Inter"], "away_team": ["Fiorentina", "Parma"], "model": ["elo", "elo"],
        "p_home": [p_home, 0.8], "p_draw": [0.3, 0.12], "p_away": [0.2, 0.08],
    })  # fmt: skip


def read(tmp_path) -> list[dict]:
    return json.loads(ledger_path("2026/27", 6, tmp_path).read_text())["forecasts"]


def test_kickoff_times_are_italian_local_time():
    # 15:00 in Rome in October (summer time, UTC+2) is 13:00 UTC
    assert kickoff_times(forecasts()).iloc[0] == pd.Timestamp("2026-10-10 13:00", tz="UTC")


def test_forecasts_are_recorded_once_and_never_changed(tmp_path):
    assert record_forecasts(forecasts(p_home=0.5), "2026/27", NOW, tmp_path) == 2
    original = read(tmp_path)

    # A later run with different probabilities must not touch what was recorded
    later = datetime(2026, 10, 3, tzinfo=timezone.utc)
    assert record_forecasts(forecasts(p_home=0.9), "2026/27", later, tmp_path) == 0
    assert read(tmp_path) == original
    assert original[0]["p_home"] == 0.5 and original[0]["recorded_at"] == "2026-10-01T12:00:00+00:00"


def test_a_new_model_is_appended_alongside_existing_entries(tmp_path):
    record_forecasts(forecasts(), "2026/27", NOW, tmp_path)
    record_forecasts(forecasts().assign(model="dixon_coles"), "2026/27", NOW, tmp_path)
    assert [f["model"] for f in read(tmp_path)] == ["elo", "elo", "dixon_coles", "dixon_coles"]


def test_nothing_is_recorded_after_kickoff(tmp_path):
    during_first_match = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)  # m1 kicked off at 13:00 UTC
    assert record_forecasts(forecasts(), "2026/27", during_first_match, tmp_path) == 1
    assert [f["match_id"] for f in read(tmp_path)] == ["m2"]


def test_next_round_is_the_matchday_of_the_next_kickoff():
    upcoming = pd.DataFrame({
        "match_id": ["a", "b", "c", "late"], "matchday": [6, 6, 7, 3],
        "date": pd.to_datetime(["2026-10-10", "2026-10-11", "2026-10-17", "2026-10-11"]),
        "time": ["15:00", "20:45", "15:00", "18:00"],
    })  # fmt: skip
    chosen = next_round(upcoming, NOW)
    # matchday 6, plus a postponed matchday-3 game played during it; not matchday 7
    assert sorted(chosen["match_id"]) == ["a", "b", "late"]
