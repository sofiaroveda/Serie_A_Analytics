"""Download Serie A results and odds from football-data.co.uk.

Raw CSVs are saved to data/raw/ exactly as downloaded; all cleaning happens in code.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
TEAM_NAMES_PATH = ROOT / "data" / "team_names.csv"

BASE_URL = "https://www.football-data.co.uk"
FIRST_SEASON_START = 2005  # 2005/06
LEAGUE = "I1"  # Serie A (Serie B is "I2")
REQUEST_PAUSE_SECONDS = 1.0  # be polite to a free data source


def season_code(start_year: int) -> str:
    """Return football-data's code for a season, e.g. 2024 -> "2425"."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def current_season_start(today: date | None = None) -> int:
    """Start year of the season in progress. Seasons roll over on 1 July."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def season_starts(first: int = FIRST_SEASON_START, today: date | None = None) -> list[int]:
    """All season start years from `first` up to the current season."""
    return list(range(first, current_season_start(today) + 1))


def season_url(start_year: int, league: str = LEAGUE) -> str:
    return f"{BASE_URL}/mmz4281/{season_code(start_year)}/{league}.csv"


def raw_season_path(start_year: int, league: str = LEAGUE) -> Path:
    return RAW_DIR / f"{league}_{season_code(start_year)}.csv"


def _download(url: str, dest: Path) -> Path:
    """Download `url` to `dest`, raising on HTTP errors or an empty response."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    if not response.content.strip():
        raise ValueError(f"Empty file downloaded from {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    return dest


def download_season(start_year: int, league: str = LEAGUE, force: bool = False) -> Path:
    """Download one season's CSV, skipping it if already on disk (unless `force`)."""
    dest = raw_season_path(start_year, league)
    if dest.exists() and not force:
        return dest
    return _download(season_url(start_year, league), dest)


def download_all_seasons(league: str = LEAGUE, today: date | None = None) -> list[Path]:
    """Download every season since 2005/06.

    Finished seasons are only downloaded once; the current season is always
    re-downloaded because new results are added to it during the year.
    """
    current = current_season_start(today)
    paths = []
    for start in season_starts(today=today):
        dest = raw_season_path(start, league)
        needs_fetch = start == current or not dest.exists()
        paths.append(download_season(start, league, force=start == current))
        if needs_fetch:
            time.sleep(REQUEST_PAUSE_SECONDS)
    return paths


def download_fixtures() -> Path:
    """Download upcoming fixtures (all leagues) with current odds."""
    return _download(f"{BASE_URL}/fixtures.csv", RAW_DIR / "fixtures.csv")


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

# Our column name -> raw column names to try, in order of preference.
# Column names vary by season (e.g. the market average was "BbAvH" before 2019/20).
ODDS_SOURCES = {
    "pin": "PS{}",  # Pinnacle, pre-match (collected a day or two before kick-off)
    "pin_close": "PSC{}",  # Pinnacle closing
    "avg": ("Avg{}", "BbAv{}"),  # market average, pre-match
    "avg_close": "AvgC{}",  # market average closing
    "b365": "B365{}",
    "b365_close": "B365C{}",
}
OUTCOMES = {"h": "H", "d": "D", "a": "A"}
ODDS_COLUMNS = [f"{book}_{o}" for book in ODDS_SOURCES for o in OUTCOMES]

MATCH_COLUMNS = [
    "match_id", "season", "date", "time",
    "home_team", "away_team", "home_goals", "away_goals", "result",
    *ODDS_COLUMNS,
]  # fmt: skip


def season_label(start_year: int) -> str:
    """Human-readable season label, e.g. 2024 -> "2024/25"."""
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def load_team_map(path: Path = TEAM_NAMES_PATH) -> dict[str, str]:
    """Load the alias -> canonical team name table."""
    table = pd.read_csv(path)
    return dict(zip(table["alias"], table["team"]))


def standardise_team_names(names: pd.Series, team_map: dict[str, str]) -> pd.Series:
    """Map raw team names to canonical names, failing loudly on unknown names.

    A new name (e.g. a newly promoted club) must be added to data/team_names.csv.
    """
    names = names.str.strip()
    unknown = sorted(set(names) - set(team_map))
    if unknown:
        raise ValueError(f"Unknown team names, add them to {TEAM_NAMES_PATH.name}: {unknown}")
    return names.map(team_map)


def parse_dates(dates: pd.Series) -> pd.Series:
    """Parse dd/mm/yy (older seasons) and dd/mm/yyyy (newer seasons) dates."""
    dates = dates.str.strip()
    two_digit_year = dates.str.len() == 8
    parsed = pd.Series(pd.NaT, index=dates.index, dtype="datetime64[ns]")
    parsed[two_digit_year] = pd.to_datetime(dates[two_digit_year], format="%d/%m/%y")
    parsed[~two_digit_year] = pd.to_datetime(dates[~two_digit_year], format="%d/%m/%Y")
    return parsed


def _extract_odds(raw: pd.DataFrame) -> pd.DataFrame:
    """Pick out the odds columns we use; missing ones are filled with NaN."""
    odds = pd.DataFrame(index=raw.index)
    for book, patterns in ODDS_SOURCES.items():
        patterns = (patterns,) if isinstance(patterns, str) else patterns
        for ours, theirs in OUTCOMES.items():
            candidates = [p.format(theirs) for p in patterns if p.format(theirs) in raw]
            column = f"{book}_{ours}"
            odds[column] = pd.to_numeric(raw[candidates[0]], errors="coerce") if candidates else float("nan")
    return odds


def _make_match_ids(dates: pd.Series, home: pd.Series, away: pd.Series) -> pd.Series:
    return dates.dt.strftime("%Y-%m-%d") + "_" + home.str.replace(" ", "") + "_" + away.str.replace(" ", "")


def load_raw_csv(path: Path) -> pd.DataFrame:
    """Read a football-data CSV (newer files start with a byte-order mark)."""
    raw = pd.read_csv(path, encoding="utf-8-sig")
    return raw.dropna(subset=["HomeTeam"]).reset_index(drop=True)  # drop blank padding rows


def clean_season(raw: pd.DataFrame, start_year: int, team_map: dict[str, str]) -> pd.DataFrame:
    """Turn one raw season file into a tidy table with one row per played match."""
    home = standardise_team_names(raw["HomeTeam"], team_map)
    away = standardise_team_names(raw["AwayTeam"], team_map)
    dates = parse_dates(raw["Date"])
    matches = pd.DataFrame(
        {
            "match_id": _make_match_ids(dates, home, away),
            "season": start_year,
            "date": dates,
            "time": raw["Time"] if "Time" in raw else pd.NA,
            "home_team": home,
            "away_team": away,
            "home_goals": raw["FTHG"].astype(int),
            "away_goals": raw["FTAG"].astype(int),
            "result": raw["FTR"].str.strip(),
        }
    )
    matches = pd.concat([matches, _extract_odds(raw)], axis=1)
    validate_matches(matches)
    return matches.sort_values(["date", "home_team"]).reset_index(drop=True)


def validate_matches(matches: pd.DataFrame) -> None:
    """Sanity checks on cleaned results. Raises ValueError if anything is off."""
    goal_diff = matches["home_goals"] - matches["away_goals"]
    expected = np.select([goal_diff > 0, goal_diff < 0], ["H", "A"], default="D")
    if not (expected == matches["result"]).all():
        bad = matches.loc[expected != matches["result"], "match_id"].tolist()
        raise ValueError(f"Result does not match the score for: {bad}")
    if (matches["home_team"] == matches["away_team"]).any():
        raise ValueError("A team is listed as playing itself")
    if matches["match_id"].duplicated().any():
        raise ValueError(f"Duplicate matches: {matches.loc[matches['match_id'].duplicated(), 'match_id'].tolist()}")
    odds = matches[ODDS_COLUMNS]
    if (odds <= 1).any().any():
        raise ValueError("Found decimal odds <= 1, which are impossible")


def clean_fixtures(raw: pd.DataFrame, team_map: dict[str, str], league: str = LEAGUE) -> pd.DataFrame:
    """Upcoming matches for one league from fixtures.csv (may be empty between rounds)."""
    raw = raw[raw["Div"] == league].reset_index(drop=True)
    home = standardise_team_names(raw["HomeTeam"], team_map)
    away = standardise_team_names(raw["AwayTeam"], team_map)
    dates = parse_dates(raw["Date"])
    fixtures = pd.DataFrame(
        {
            "match_id": _make_match_ids(dates, home, away),
            "date": dates,
            "time": raw["Time"],
            "home_team": home,
            "away_team": away,
        }
    )
    return pd.concat([fixtures, _extract_odds(raw)], axis=1)


def build_matches(start_years: list[int], league: str = LEAGUE) -> pd.DataFrame:
    """Clean and combine all downloaded seasons into one table."""
    team_map = load_team_map()
    seasons = [clean_season(load_raw_csv(raw_season_path(y, league)), y, team_map) for y in start_years]
    matches = pd.concat(seasons, ignore_index=True)
    return matches[MATCH_COLUMNS]


def main() -> None:
    """Download everything, clean it and write data/processed/*.csv."""
    years = season_starts()
    print(f"Downloading {len(years)} seasons ({season_label(years[0])} to {season_label(years[-1])})...")
    download_all_seasons()
    download_fixtures()

    matches = build_matches(years)
    fixtures = clean_fixtures(load_raw_csv(RAW_DIR / "fixtures.csv"), load_team_map())

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    matches.to_csv(PROCESSED_DIR / "matches.csv", index=False)
    fixtures.to_csv(PROCESSED_DIR / "fixtures.csv", index=False)

    print(f"Saved {len(matches)} matches and {len(fixtures)} upcoming fixtures to {PROCESSED_DIR}")
    print(matches.groupby("season").agg(matches=("match_id", "size"), pinnacle_closing=("pin_close_h", "count")))


if __name__ == "__main__":
    main()
