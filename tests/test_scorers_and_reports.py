"""Tests for reading goal scorers and writing match reports."""

from pipeline.report import discipline_sentence, expectation_sentence, match_report, result_sentence
from pipeline.scorers import parse_file, scorers_by_match, tidy_name

SAMPLE = """= Italy | Serie A 2025/26

Sat Aug 23 2025
  16:30   Sassuolo  0-2 (0-1)  Napoli
                  (Scott McTominay 17', Kevin DE BRUYNE 57')
  20:45   Milan  1-2 (1-1)  Cremonese
                  (Strahinja PAVLOVIC 45+1';
                   Federico Baschirotto 28', Federico Bonazzoli 61')
  20:45   Atalanta  1-1 (0-1)  Pisa
                  (Gianluca Scamacca 50'; Isak HIEN 26'(og))
  18:30   Genoa  0-0 (0-0)  Lecce
  18:30   Como  3-0 (1-0)  Lazio
                  (Nico PAZ 12', 60', Anastasios Douvikas 88' (pen))
  20:45   Roma  2-0 (1-0)  Bologna
                  (WESLEY 53')
"""
TEAMS = {t: t for t in ["Sassuolo", "Napoli", "Milan", "Cremonese", "Atalanta", "Pisa", "Genoa", "Lecce", "Como", "Lazio", "Roma", "Bologna"]}


def test_names_in_capitals_are_tidied():
    assert tidy_name("Kevin DE BRUYNE") == "Kevin De Bruyne" and tidy_name("Scott McTominay") == "Scott McTominay"


def test_scorers_are_read_and_assigned_to_the_right_team():
    games = {(m.home, m.away): m for m in parse_file(SAMPLE)}
    assert [g["player"] for g in games[("Sassuolo", "Napoli")].away_scorers] == ["Scott McTominay", "Kevin De Bruyne"]
    milan = games[("Milan", "Cremonese")]
    assert milan.home_scorers[0]["minute"] == "45+1" and len(milan.away_scorers) == 2  # scorers over two lines
    assert games[("Atalanta", "Pisa")].away_scorers[0]["own_goal"] is True
    como = games[("Como", "Lazio")].home_scorers
    assert [g["player"] for g in como] == ["Nico Paz", "Nico Paz", "Anastasios Douvikas"]  # 12', 60' = two goals
    assert como[2]["penalty"] is True


def test_scorers_that_dont_add_up_are_left_out():
    found = scorers_by_match(SAMPLE, TEAMS)
    assert ("Sassuolo", "Napoli") in found and ("Como", "Lazio") in found
    assert ("Roma", "Bologna") not in found  # 2-0 but only one scorer listed
    assert ("Genoa", "Lecce") not in found  # 0-0: nothing to show


def test_unknown_team_names_are_skipped_not_fatal():
    assert ("Sassuolo", "Napoli") not in scorers_by_match(SAMPLE, {"Milan": "Milan", "Cremonese": "Cremonese"})


def game(**extra) -> dict:
    return {"home_team": "Inter", "away_team": "Parma", "home_goals": 0, "away_goals": 1, "result": "A",
            "dc_home": 0.75, "dc_draw": 0.16, "dc_away": 0.09, **extra}  # fmt: skip


def test_result_and_expectation_sentences():
    assert result_sentence(game()) == "Parma stunned Inter 1–0 away from home."
    assert "only a 9% chance" in expectation_sentence(game())
    draw = game(home_goals=1, away_goals=1, result="D")
    assert result_sentence(draw) == "Inter and Parma drew 1–1."
    assert expectation_sentence(draw) == "Inter were favourites (75%) but couldn't find a winner."
    assert result_sentence(game(home_goals=4, away_goals=0, result="H")).startswith("Inter thrashed Parma 4–0")


def test_red_cards():
    assert discipline_sentence(game(home_red=1, away_red=0)) == "Inter finished with ten men."
    assert discipline_sentence(game(home_red=0, away_red=2)) == "Parma finished with nine men."
    assert discipline_sentence(game(home_red=0, away_red=0)) is None


def test_report_uses_only_available_facts():
    report = match_report(game(home_shots=15, away_shots=6, home_on_target=4, away_on_target=2,
                               home_xg=1.9, away_xg=0.6, home_red=0, away_red=1),
                          before={"Inter": {"p_title": 0.56, "p_top4": 0.93, "p_relegation": 0.0}},
                          after={"Inter": {"p_title": 0.48, "p_top4": 0.90, "p_relegation": 0.0}})  # fmt: skip
    assert "Inter had 15 shots (4 on target) to Parma's 6 (2)." in report
    assert "Parma won despite creating less (expected goals: Inter 1.9, Parma 0.6)." in report
    assert "Parma finished with ten men." in report
    assert "Inter's title chance went from 56% to 48%" in report
    assert "Goals:" not in report  # no scorers available


def test_two_moves_are_joined_into_one_sentence():
    report = match_report(game(), before={"Inter": {"p_title": 0.56, "p_top4": 0.9, "p_relegation": 0}, "Parma": {"p_title": 0, "p_top4": 0, "p_relegation": 0.37}},
                          after={"Inter": {"p_title": 0.48, "p_top4": 0.9, "p_relegation": 0}, "Parma": {"p_title": 0, "p_top4": 0, "p_relegation": 0.28}})  # fmt: skip
    assert report.count("After the round") == 1
    assert "Inter's title chance went from 56% to 48%, and Parma's relegation chance from 37% to 28%." in report
