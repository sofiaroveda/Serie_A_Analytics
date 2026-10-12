"""Faster results from football-data.org (free plan; "Data provided by football-data.org").

football-data.co.uk, our main source, adds a round's results a day or two after it ends.
football-data.org has each score within hours of the final whistle, so between the two
we use it to fill the gap:

- a match football-data.co.uk doesn't have yet is added from football-data.org (score only:
  odds and stats such as shots and corners arrive later from football-data.co.uk);
- once football-data.co.uk has the match too, its row is used, and the two scores must agree,
  or the update stops rather than publishing a wrong result.

The access key is read from the FOOTBALL_DATA_ORG_KEY environment variable (a GitHub Actions
secret), never stored in the code. Without a key this source is simply skipped.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API_URL = "https://api.football-data.org/v4/competitions/SA/matches"
KEY_VARIABLE = "FOOTBALL_DATA_ORG_KEY"
ITALY = ZoneInfo("Europe/Rome")
SOURCE_MAIN, SOURCE_LIVE = "football-data.co.uk", "football-data.org"


def api_key() -> str | None:
    return os.environ.get(KEY_VARIABLE) or None


def download(season: int, key: str, dest: Path) -> Path:
    """Save the finished Serie A matches of `season` (start year) as raw JSON."""
    response = requests.get(API_URL, params={"season": season, "status": "FINISHED"},
                            headers={"X-Auth-Token": key}, timeout=30)  # fmt: skip
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(response.text)
    return dest


def parse(payload: dict, season: int, team_map: dict[str, str]) -> pd.DataFrame:
    """Finished matches as rows in our format (score only). Unknown team names are skipped with a warning."""
    rows, unknown = [], set()
    for m in payload.get("matches", []):
        full_time = (m.get("score") or {}).get("fullTime") or {}
        if m.get("status") != "FINISHED" or full_time.get("home") is None:
            continue
        names = []
        for side in ("homeTeam", "awayTeam"):
            team = m[side]
            name = team_map.get(team.get("name")) or team_map.get(team.get("shortName"))
            if not name:
                unknown.add(team.get("name"))
            names.append(name)
        if None in names:
            continue
        kickoff = pd.Timestamp(m["utcDate"]).tz_convert(ITALY)  # dates and times in Italian local time, like our other sources
        hg, ag = int(full_time["home"]), int(full_time["away"])
        rows.append({
            "season": season, "date": kickoff.tz_localize(None).normalize(), "time": kickoff.strftime("%H:%M"),
            "home_team": names[0], "away_team": names[1], "home_goals": hg, "away_goals": ag,
            "result": "H" if hg > ag else "A" if hg < ag else "D",
        })  # fmt: skip
    if unknown:
        print(f"Warning: football-data.org team names not in team_names.csv, skipped: {sorted(unknown)}")
    return pd.DataFrame(rows, columns=["season", "date", "time", "home_team", "away_team", "home_goals", "away_goals", "result"])


def fill_gaps(matches: pd.DataFrame, live: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Add live results that `matches` doesn't have yet; raise if the two sources disagree on a score.

    Returns the combined table and how many matches were added.
    """
    from pipeline.data import MATCH_COLUMNS, make_match_ids  # local import: data imports nothing from here

    matches = matches.assign(source=matches.get("source", SOURCE_MAIN))
    if live.empty:
        return matches, 0
    key = ["season", "home_team", "away_team"]
    both = live.merge(matches[[*key, "home_goals", "away_goals", "match_id"]], on=key, suffixes=("", "_main"))
    wrong = both[(both["home_goals"] != both["home_goals_main"]) | (both["away_goals"] != both["away_goals_main"])]
    if len(wrong):
        raise ValueError(f"football-data.org and football-data.co.uk disagree on: {wrong['match_id'].tolist()}")

    new = live.merge(matches[key], on=key, how="left", indicator=True)
    new = new[new["_merge"] == "left_only"].drop(columns="_merge")
    if new.empty:
        return matches, 0
    new = new.assign(match_id=make_match_ids(new["date"], new["home_team"], new["away_team"]), source=SOURCE_LIVE)
    new = new.reindex(columns=[*MATCH_COLUMNS, "source"])  # odds and stats stay blank until the main source has them
    combined = pd.concat([matches, new], ignore_index=True).sort_values(["date", "home_team"]).reset_index(drop=True)
    return combined, len(new)


def load_saved(path: Path) -> dict:
    return json.loads(path.read_text())
