"""Write the JSON files the website reads (site/data/*.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.data import PROCESSED_DIR, ROOT, current_season_start, season_label
from pipeline.elo import EloParams, predict_fixtures, predict_matches
from pipeline.evaluate import TEST_SEASONS, base_rate_forecast, compare_with_market, rps
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


def _with_model(matches: pd.DataFrame, predictions: pd.DataFrame | None, name: str) -> pd.DataFrame:
    """Add a model's probabilities as {name}_home / {name}_draw / {name}_away columns (null if missing)."""
    cols = [f"{name}_home", f"{name}_draw", f"{name}_away"]
    if predictions is None or predictions.empty:
        return matches.assign(**{c: np.nan for c in cols})
    probs = predictions[["match_id", "p_home", "p_draw", "p_away"]].copy()
    probs.columns = ["match_id", *cols]
    probs[cols] = probs[cols].round(4)
    return matches.merge(probs, on="match_id", how="left")


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    """DataFrame -> list of dicts, with dates as YYYY-MM-DD and NaN as null."""
    df = df[columns].copy()
    for col in df.select_dtypes("datetime").columns:
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict(orient="records")


def build_site_data(
    matches: pd.DataFrame,
    fixtures: pd.DataFrame,
    elo_results: pd.DataFrame | None = None,
    elo_fixtures: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Everything the site needs, keyed by output file name.

    `elo_results` / `elo_fixtures` are walk-forward Elo predictions (match_id,
    p_home, p_draw, p_away) for played matches and upcoming fixtures.
    """
    season = int(matches["season"].max())
    played = _with_probabilities(matches[matches["season"] == season], CLOSING_SOURCES)
    played = _with_model(played, elo_results, "elo")
    played = played.sort_values(["date", "time", "home_team"], ascending=[False, False, True])
    upcoming = _with_probabilities(fixtures, PRE_MATCH_SOURCES)
    upcoming = _with_model(upcoming, elo_fixtures, "elo").sort_values(["date", "time", "home_team"])

    # How often did the market's favourite (highest probability) win?
    with_probs = played.dropna(subset=["p_home"])
    favourite = with_probs[["p_home", "p_draw", "p_away"]].to_numpy().argmax(axis=1)
    outcome = with_probs["result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()

    # This season's scoreboard: Elo vs the market on the same matches
    both = played.dropna(subset=["p_home", "elo_home"])
    scoreboard = None
    if len(both):
        scoreboard = {
            "matches": len(both),
            "elo_rps": round(rps(both[["elo_home", "elo_draw", "elo_away"]].to_numpy(), both["result"]), 4),
            "market_rps": round(rps(both[["p_home", "p_draw", "p_away"]].to_numpy(), both["result"]), 4),
        }

    match_cols = [
        "match_id", "date", "time", "home_team", "away_team",
        "p_home", "p_draw", "p_away", "odds_source", "elo_home", "elo_draw", "elo_away",
    ]  # fmt: skip
    return {
        "summary": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "season": season_label(season),
            "matches_played": len(played),
            "last_result_date": played["date"].max().strftime("%Y-%m-%d") if len(played) else None,
            "favourite_win_rate": round(float(np.mean(favourite == outcome)), 4) if len(with_probs) else None,
            "scoreboard": scoreboard,
        },
        "table": _records(league_table(played), [
            "position", "team", "played", "won", "drawn", "lost",
            "goals_for", "goals_against", "goal_diff", "points",
        ]),  # fmt: skip
        "results": _records(played, [*match_cols, "home_goals", "away_goals", "result"]),
        "fixtures": _records(upcoming, match_cols),
    }


def backtest_summary(matches: pd.DataFrame, elo_predictions: pd.DataFrame) -> dict[str, object]:
    """Walk-forward test results: Elo vs Pinnacle closing vs base rates, per test season."""
    preds = elo_predictions[elo_predictions["season"].isin(TEST_SEASONS)]
    # Score everything on the same matches: those with Pinnacle closing odds
    covered = matches.dropna(subset=["pin_close_h", "pin_close_d", "pin_close_a"])["match_id"]
    preds = preds[preds["match_id"].isin(covered)]
    base = preds[["match_id"]].copy()
    base[["p_home", "p_draw", "p_away"]] = base_rate_forecast(matches, preds)

    table = pd.concat([
        compare_with_market(preds, matches, "elo", markets={"pinnacle": "pin_close"}),
        compare_with_market(base, matches, "base_rates", markets={}),
    ])  # fmt: skip
    wide = table.pivot(index="season", columns="forecaster", values="rps")
    counts = table[table["forecaster"] == "elo"].set_index("season")["matches"]

    def row(label, key):
        return {
            "season": label, "matches": int(counts[key]),
            **{name: round(float(wide.loc[key, name]), 4) for name in ("elo", "pinnacle", "base_rates")},
        }  # fmt: skip

    return {
        "seasons": [row(season_label(int(s)), s) for s in wide.index if s != "All"],
        "overall": row(f"{season_label(min(TEST_SEASONS))} to {season_label(max(TEST_SEASONS))}", "All"),
        "elo_params": EloParams().__dict__,
    }


def write_site_data(out_dir: Path = SITE_DATA_DIR) -> None:
    """Read the processed CSVs, run the models and write one JSON file per page dataset."""
    matches = pd.read_csv(PROCESSED_DIR / "matches.csv", parse_dates=["date"])
    fixtures = pd.read_csv(PROCESSED_DIR / "fixtures.csv", parse_dates=["date"])

    params = EloParams()
    elo_results = predict_matches(matches, params, first_season=min(TEST_SEASONS))
    elo_fixtures = predict_fixtures(matches, fixtures, params, season=current_season_start()) if len(fixtures) else None

    content = build_site_data(matches, fixtures, elo_results, elo_fixtures)
    content["backtest"] = backtest_summary(matches, elo_results)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        (out_dir / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote site data to {out_dir}")


if __name__ == "__main__":
    write_site_data()
