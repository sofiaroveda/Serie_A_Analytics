"""Write the JSON files the website reads (site/data/*.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.data import PROCESSED_DIR, ROOT, season_label
from pipeline.market import best_available_probabilities

SITE_DATA_DIR = ROOT / "site" / "data"

# Benchmark order (see CLAUDE.md, Market comparison): Pinnacle closing where it
# exists, otherwise the market-average closing price for that match.
CLOSING_SOURCES = ["pin_close", "avg_close", "b365_close"]
PRE_MATCH_SOURCES = ["pin", "avg", "b365"]
SOURCE_LABELS = {
    "pin_close": "Pinnacle closing",
    "avg_close": "Market average closing",
    "b365_close": "Bet365 closing",
    "pin": "Pinnacle",
    "avg": "Market average",
    "b365": "Bet365",
}


def league_table(matches: pd.DataFrame) -> pd.DataFrame:
    """Standings from results: 3 points for a win, 1 for a draw.

    Ties are broken by goal difference, then goals scored (Serie A actually uses
    head-to-head first, which we can add later).
    """
    home = pd.DataFrame({
        "team": matches["home_team"], "gf": matches["home_goals"], "ga": matches["away_goals"],
    })  # fmt: skip
    away = pd.DataFrame({
        "team": matches["away_team"], "gf": matches["away_goals"], "ga": matches["home_goals"],
    })  # fmt: skip
    games = pd.concat([home, away], ignore_index=True)
    games["won"] = games["gf"] > games["ga"]
    games["drawn"] = games["gf"] == games["ga"]
    games["lost"] = games["gf"] < games["ga"]

    table = games.groupby("team").agg(
        played=("gf", "size"), won=("won", "sum"), drawn=("drawn", "sum"), lost=("lost", "sum"),
        goals_for=("gf", "sum"), goals_against=("ga", "sum"),
    )  # fmt: skip
    table["goal_diff"] = table["goals_for"] - table["goals_against"]
    table["points"] = 3 * table["won"] + table["drawn"]
    table = table.reset_index().sort_values(
        ["points", "goal_diff", "goals_for", "team"], ascending=[False, False, False, True]
    )
    table.insert(0, "position", range(1, len(table) + 1))
    return table.reset_index(drop=True)


def _with_probabilities(matches: pd.DataFrame, sources: list[str]) -> pd.DataFrame:
    probs, source = best_available_probabilities(matches, sources)
    out = matches.copy()
    out[["p_home", "p_draw", "p_away"]] = probs.round(4)
    out["odds_source"] = source.map(SOURCE_LABELS)
    return out


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    """DataFrame -> list of dicts, with dates as YYYY-MM-DD and NaN as null."""
    df = df[columns].copy()
    for col in df.select_dtypes("datetime").columns:
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict(orient="records")


def build_site_data(matches: pd.DataFrame, fixtures: pd.DataFrame) -> dict[str, object]:
    """Everything the site needs, keyed by output file name."""
    season = int(matches["season"].max())
    played = _with_probabilities(matches[matches["season"] == season], CLOSING_SOURCES)
    played = played.sort_values(["date", "time", "home_team"], ascending=[False, False, True])
    upcoming = _with_probabilities(fixtures, PRE_MATCH_SOURCES).sort_values(["date", "time", "home_team"])

    # How often did the market's favourite (highest probability) win?
    with_probs = played.dropna(subset=["p_home"])
    favourite = with_probs[["p_home", "p_draw", "p_away"]].to_numpy().argmax(axis=1)
    outcome = with_probs["result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()

    match_cols = ["match_id", "date", "time", "home_team", "away_team", "p_home", "p_draw", "p_away", "odds_source"]
    return {
        "summary": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "season": season_label(season),
            "matches_played": len(played),
            "last_result_date": played["date"].max().strftime("%Y-%m-%d") if len(played) else None,
            "favourite_win_rate": round(float(np.mean(favourite == outcome)), 4) if len(with_probs) else None,
        },
        "table": _records(league_table(played), [
            "position", "team", "played", "won", "drawn", "lost",
            "goals_for", "goals_against", "goal_diff", "points",
        ]),  # fmt: skip
        "results": _records(played, [*match_cols, "home_goals", "away_goals", "result"]),
        "fixtures": _records(upcoming, match_cols),
    }


def write_site_data(out_dir: Path = SITE_DATA_DIR) -> None:
    """Read the processed CSVs and write one JSON file per key of build_site_data."""
    matches = pd.read_csv(PROCESSED_DIR / "matches.csv", parse_dates=["date"])
    fixtures = pd.read_csv(PROCESSED_DIR / "fixtures.csv", parse_dates=["date"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, content in build_site_data(matches, fixtures).items():
        (out_dir / f"{name}.json").write_text(json.dumps(content, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote site data to {out_dir}")


if __name__ == "__main__":
    write_site_data()
