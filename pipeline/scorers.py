"""Goal scorers from openfootball's Serie A text files (public domain).

openfootball volunteers add scorers after matches, e.g.

    16:30   Sassuolo  0-2 (0-1)  Napoli
                    (Scott McTominay 17', Kevin DE BRUYNE 57')

Home scorers come before a ";", away scorers after it (if only one side scored,
there is no ";"). Own goals are marked "(og)" and listed under the team they
counted for. Scorers are optional extras on the site: a match whose scorers don't
add up to its score is skipped rather than shown wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SCORERS_URL = "https://raw.githubusercontent.com/openfootball/italy/master/{season}/1-seriea.txt"

# "Udinese Calcio   v Como 1907   1-1 (1-0)" (newer files) or "Sassuolo  0-2 (0-1)  Napoli" (older files)
_TIME = r"(?:\d{1,2}[:.]\d{2}\s+)?"
_HALF_TIME = r"(?:\s+\(\d+-\d+\))?"
MATCH_V = re.compile(rf"^\s*{_TIME}(?P<home>\S.*?)\s+v\s+(?P<away>\S.*?)\s+(?P<hg>\d+)-(?P<ag>\d+){_HALF_TIME}\s*$")
MATCH_SCORE_BETWEEN = re.compile(rf"^\s*{_TIME}(?P<home>\S.*?)\s+(?P<hg>\d+)-(?P<ag>\d+){_HALF_TIME}\s+(?P<away>\S.*?)\s*$")
GOAL = re.compile(r"^(?P<name>.*?)\s*(?P<minute>\d+(?:\+\d+)?)'\s*(?:\((?P<note>og|pen\.?|p)\))?\s*$", re.IGNORECASE)


@dataclass
class ParsedMatch:
    home: str
    away: str
    home_goals: int
    away_goals: int
    home_scorers: list[dict] = field(default_factory=list)
    away_scorers: list[dict] = field(default_factory=list)

    def scorers_add_up(self) -> bool:
        return len(self.home_scorers) == self.home_goals and len(self.away_scorers) == self.away_goals


def tidy_name(name: str) -> str:
    """openfootball writes some surnames in capitals ("Kevin DE BRUYNE"): make them "Kevin De Bruyne"."""
    return " ".join(w.title() if w.isupper() and len(w) > 1 else w for w in name.split())


def parse_goals(text: str) -> list[dict]:
    """ "Lautaro Martinez 12', 45'+2', Nico PAZ 73' (pen)" -> one dict per goal."""
    goals, name = [], ""
    for entry in (e.strip() for e in text.split(",")):
        found = GOAL.match(entry)
        if not found:
            raise ValueError(f"Can't read goal entry: {entry!r}")
        name = tidy_name(found["name"]) or name  # no name = another goal by the previous scorer
        note = (found["note"] or "").lower().rstrip(".")
        goals.append({"player": name, "minute": found["minute"], "own_goal": note == "og", "penalty": note in ("pen", "p")})
    return goals


def parse_file(text: str) -> list[ParsedMatch]:
    """Every played match in the file, with its scorers when they are listed."""
    matches: list[ParsedMatch] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        found = None if line.lstrip().startswith(("#", "=", "▪", "(")) else (MATCH_V.match(line) or MATCH_SCORE_BETWEEN.match(line))
        i += 1
        if not found:
            continue
        match = ParsedMatch(found["home"].strip(), found["away"].strip(), int(found["hg"]), int(found["ag"]))
        # Scorer lines follow in brackets, possibly over several lines
        if i < len(lines) and lines[i].strip().startswith("("):
            block = lines[i].strip()
            i += 1
            while not block.endswith(")") and i < len(lines):
                block += " " + lines[i].strip()
                i += 1
            try:
                _assign_goals(match, block[1:-1])
            except ValueError:
                match.home_scorers, match.away_scorers = [], []  # unreadable: skip this match's scorers
        matches.append(match)
    return matches


def _assign_goals(match: ParsedMatch, inside: str) -> None:
    if ";" in inside:
        home_part, away_part = inside.split(";", 1)
        match.home_scorers = parse_goals(home_part) if home_part.strip() else []
        match.away_scorers = parse_goals(away_part) if away_part.strip() else []
    elif match.away_goals == 0:
        match.home_scorers = parse_goals(inside)
    elif match.home_goals == 0:
        match.away_scorers = parse_goals(inside)
    # both teams scored but no ";": we can't tell whose goals are whose, so leave them out


def scorers_by_match(text: str, team_map: dict[str, str]) -> dict[tuple[str, str], dict]:
    """(home_team, away_team) -> {"home": [...], "away": [...]} for matches whose scorers add up.

    Team names are mapped to our names; unknown names are skipped (scorers are an extra,
    so an unfamiliar spelling mustn't stop the daily update).
    """
    result = {}
    for m in parse_file(text):
        if not (m.home_scorers or m.away_scorers) or not m.scorers_add_up():
            continue
        home, away = team_map.get(m.home), team_map.get(m.away)
        if home and away:
            result[(home, away)] = {"home": m.home_scorers, "away": m.away_scorers}
    return result
