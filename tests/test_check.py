"""Tests for the pre-publish checks."""

import copy

from pipeline.check import check_matches, check_site_data, check_table, compare_ledgers


def match(i: int, matchday: int, **extra) -> dict:
    return {"match_id": f"m{i}", "matchday": matchday, "status": "upcoming", "home_team": f"T{i}",
            "away_team": f"U{i}", "home_goals": None, "result": None,
            "p_home": None, "p_draw": None, "p_away": None,
            "elo_home": 0.5, "elo_draw": 0.3, "elo_away": 0.2, "dc_home": 0.5, "dc_draw": 0.3, "dc_away": 0.2,
            **extra}  # fmt: skip


def season(matchdays: int = 2) -> list[dict]:
    return [match(md * 10 + k, md) for md in range(1, matchdays + 1) for k in range(10)]


def test_complete_season_passes():
    assert check_matches(season(), matchdays=2) == []


def test_missing_match_is_caught():
    assert any("expected 20" in e for e in check_matches(season()[:-1], matchdays=2))


def test_probabilities_that_dont_add_up_are_caught():
    matches = season()
    matches[3]["dc_home"] = 0.9
    assert any("don't add up" in e for e in check_matches(matches, matchdays=2))


def test_played_match_needs_a_score_and_prediction():
    matches = season()
    matches[0].update(status="played", home_goals=None, result=None)
    matches[1].update(status="played", home_goals=1, result="H", dc_home=None, dc_draw=None, dc_away=None)
    errors = check_matches(matches, matchdays=2)
    assert any("missing a score" in e for e in errors) and any("no model prediction" in e for e in errors)


def test_table_must_agree_with_results():
    matches = [{"home_team": "A", "away_team": "B", "status": "played"}]
    good = [{"team": "A", "played": 1, "won": 1, "drawn": 0, "lost": 0, "points": 3},
            {"team": "B", "played": 1, "won": 0, "drawn": 0, "lost": 1, "points": 0}]  # fmt: skip
    assert check_table(good, matches) == []
    bad = copy.deepcopy(good)
    bad[0]["points"] = 4
    assert any("points" in e for e in check_table(bad, matches))


def ledger(*entries) -> dict:
    return {"season": "2026/27", "matchday": 6, "forecasts": list(entries)}


ENTRY = {"match_id": "m1", "model": "dc", "p_home": 0.5, "p_draw": 0.3, "p_away": 0.2, "recorded_at": "2026-10-01"}


def test_appending_to_the_record_is_allowed():
    new_entry = {**ENTRY, "model": "elo"}
    assert compare_ledgers(ledger(ENTRY), ledger(ENTRY, new_entry), "md6") == []


def test_changing_removing_or_deleting_a_forecast_is_caught():
    assert "changed" in compare_ledgers(ledger(ENTRY), ledger({**ENTRY, "p_home": 0.6}), "md6")[0]
    assert "removed" in compare_ledgers(ledger(ENTRY), ledger(), "md6")[0]
    assert "deleted" in compare_ledgers(ledger(ENTRY), None, "md6")[0]


def test_the_published_site_data_passes():
    # The committed site/data files must always pass the checks
    assert check_site_data() == []
