"""Write the JSON files the website reads (site/data/*.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.data import PROCESSED_DIR, ROOT, make_match_ids, season_label
from pipeline import dixon_coles, elo
from pipeline.evaluate import TEST_SEASONS, base_rate_forecast, compare_with_market, rps
from pipeline.ledger import next_round, record_forecasts
from pipeline.market import best_available_probabilities

SITE_DATA_DIR = ROOT / "site" / "data"

# Benchmark order (see CLAUDE.md, Market comparison): Pinnacle closing where it
# exists, otherwise the market-average closing price for that match.
CLOSING_SOURCES = ["pin_close", "avg_close", "b365_close"]
PRE_MATCH_SOURCES = ["pin", "avg", "b365"]
# Our models: key used in the data files -> display name
MODELS = {"elo": "Elo", "dc": "Dixon-Coles"}
# Extra model outputs copied to the site when a model provides them (Dixon-Coles does)
EXTRA_OUTPUTS = {"exp_home_goals": "xg_home", "exp_away_goals": "xg_away", "p_over_2_5": "over_2_5", "p_btts": "btts"}

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
    """Add a model's outputs as {name}_home, {name}_draw, {name}_away (+ extras). Null where missing."""
    renames = {"p_home": f"{name}_home", "p_draw": f"{name}_draw", "p_away": f"{name}_away"}
    if predictions is None or predictions.empty:
        return matches.assign(**{c: np.nan for c in renames.values()})
    renames.update({k: f"{name}_{v}" for k, v in EXTRA_OUTPUTS.items() if k in predictions})
    outputs = predictions[["match_id", *renames]].rename(columns=renames)
    return matches.merge(outputs.round(4), on="match_id", how="left")


def _model_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.split("_")[0] in MODELS]


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    """DataFrame -> list of dicts, with dates as YYYY-MM-DD and NaN as null."""
    df = df[columns].copy()
    for col in df.select_dtypes("datetime").columns:
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict(orient="records")


def upcoming_from_schedule(schedule: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Scheduled matches of the season that haven't been played yet."""
    played = matches.loc[matches["season"] == schedule["season"].iloc[0], ["home_team", "away_team"]]
    upcoming = schedule.merge(played, on=["home_team", "away_team"], how="left", indicator=True)
    upcoming = upcoming[upcoming["_merge"] == "left_only"].drop(columns=["_merge", "home_goals", "away_goals"])
    upcoming["match_id"] = make_match_ids(upcoming["date"], upcoming["home_team"], upcoming["away_team"])
    return upcoming.reset_index(drop=True)


def build_site_data(
    matches: pd.DataFrame,
    fixtures: pd.DataFrame,
    schedule: pd.DataFrame,
    predictions: dict[str, pd.DataFrame] | None = None,
) -> dict[str, object]:
    """Everything the site needs, keyed by output file name.

    `schedule` is this season's full fixture list with matchdays. `predictions`
    maps a model key in MODELS to its forecasts (match_id, p_home, p_draw,
    p_away, optional extras) for played and upcoming matches.
    """
    predictions = predictions or {}
    season = int(schedule["season"].iloc[0])
    matchdays = schedule[["home_team", "away_team", "matchday"]]

    played = _with_probabilities(matches[matches["season"] == season], CLOSING_SOURCES)
    played = played.merge(matchdays, on=["home_team", "away_team"], how="left", validate="one_to_one")
    played["status"] = "played"

    # Upcoming: market odds (when bookmakers have published them) joined by team pairing
    upcoming = upcoming_from_schedule(schedule, matches)
    odds = _with_probabilities(fixtures, PRE_MATCH_SOURCES)[["home_team", "away_team", "p_home", "p_draw", "p_away", "odds_source"]]
    upcoming = upcoming.merge(odds, on=["home_team", "away_team"], how="left")
    upcoming["status"] = "upcoming"

    season_matches = pd.concat([played, upcoming], ignore_index=True)
    for name in MODELS:
        season_matches = _with_model(season_matches, predictions.get(name), name)
    season_matches = season_matches.sort_values(["matchday", "date", "time", "home_team"])
    played = season_matches[season_matches["status"] == "played"]

    # How often did the market's favourite (highest probability) win?
    with_probs = played.dropna(subset=["p_home"])
    favourite = with_probs[["p_home", "p_draw", "p_away"]].to_numpy().argmax(axis=1)
    outcome = with_probs["result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()

    # This season's scoreboard: every model and the market, on the same matches
    scored = played.dropna(subset=["p_home", *[f"{name}_home" for name in predictions]])
    scoreboard = None
    if len(scored) and predictions:
        scoreboard = {"matches": len(scored)}
        for key, prefix in [("market", "p"), *[(name, name) for name in predictions]]:
            probs = scored[[f"{prefix}_home", f"{prefix}_draw", f"{prefix}_away"]].to_numpy()
            scoreboard[f"{key}_rps"] = round(rps(probs, scored["result"]), 4)

    # The matchday to show first: the earliest one with a match still to play
    next_matchday = int(upcoming["matchday"].min()) if len(upcoming) else int(schedule["matchday"].max())

    return {
        "summary": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "season": season_label(season),
            "matches_played": len(played),
            "last_result_date": played["date"].max().strftime("%Y-%m-%d") if len(played) else None,
            "favourite_win_rate": round(float(np.mean(favourite == outcome)), 4) if len(with_probs) else None,
            "scoreboard": scoreboard,
            "current_matchday": next_matchday,
            "matchdays": int(schedule["matchday"].max()),
        },
        "table": _records(league_table(played), [
            "position", "team", "played", "won", "drawn", "lost",
            "goals_for", "goals_against", "goal_diff", "points",
        ]),  # fmt: skip
        "matches": _records(season_matches, [
            "match_id", "matchday", "status", "date", "time", "home_team", "away_team",
            "home_goals", "away_goals", "result", "p_home", "p_draw", "p_away", "odds_source",
            *_model_columns(season_matches),
        ]),  # fmt: skip
    }


def backtest_summary(matches: pd.DataFrame, predictions: dict[str, pd.DataFrame]) -> dict[str, object]:
    """Walk-forward test results per test season: each model vs Pinnacle closing vs base rates."""
    # Score everything on the same matches: test seasons with Pinnacle closing odds
    covered = matches.dropna(subset=["pin_close_h", "pin_close_d", "pin_close_a"])
    covered = covered.loc[covered["season"].isin(TEST_SEASONS), "match_id"]
    base = pd.DataFrame({"match_id": covered})
    base = base.merge(matches[["match_id", "season"]], on="match_id")
    base[["p_home", "p_draw", "p_away"]] = base_rate_forecast(matches, base)

    tables = [compare_with_market(base, matches, "base_rates", markets={"pinnacle": "pin_close"})]
    for name, preds in predictions.items():
        tables.append(compare_with_market(preds[preds["match_id"].isin(covered)], matches, name, markets={}))
    table = pd.concat(tables)
    wide = table.pivot(index="season", columns="forecaster", values="rps")
    counts = table[table["forecaster"] == "pinnacle"].set_index("season")["matches"]
    forecasters = ["base_rates", *predictions, "pinnacle"]

    def row(label, key):
        return {"season": label, "matches": int(counts[key]),
                **{name: round(float(wide.loc[key, name]), 4) for name in forecasters}}  # fmt: skip

    return {
        "forecasters": {"base_rates": "Base rates", **{k: MODELS[k] for k in predictions}, "pinnacle": "Pinnacle"},
        "seasons": [row(season_label(int(s)), s) for s in wide.index if s != "All"],
        "overall": row(f"{season_label(min(TEST_SEASONS))} to {season_label(max(TEST_SEASONS))}", "All"),
        "params": {"elo": elo.EloParams().__dict__, "dc": dixon_coles.DCParams().__dict__},
    }


def write_site_data(out_dir: Path = SITE_DATA_DIR) -> None:
    """Read the processed CSVs, run the models and write one JSON file per page dataset."""
    matches = pd.read_csv(PROCESSED_DIR / "matches.csv", parse_dates=["date"])
    fixtures = pd.read_csv(PROCESSED_DIR / "fixtures.csv", parse_dates=["date"])
    schedule = pd.read_csv(PROCESSED_DIR / "schedule.csv", parse_dates=["date"])
    season = int(schedule["season"].iloc[0])
    upcoming = upcoming_from_schedule(schedule, matches)
    first = min(TEST_SEASONS)

    # Walk-forward forecasts for played matches, and latest forecasts for upcoming ones
    played_preds = {
        "elo": elo.predict_matches(matches, elo.EloParams(), first_season=first),
        "dc": dixon_coles.predict_matches(matches, dixon_coles.DCParams(), first_season=first),
    }
    upcoming_preds = {
        "elo": elo.predict_fixtures(matches, upcoming, elo.EloParams(), season),
        "dc": dixon_coles.predict_fixtures(matches, upcoming, dixon_coles.DCParams(), season),
    } if len(upcoming) else {}  # fmt: skip

    # Lock in forecasts for the next round before kick-off (append-only record)
    now = datetime.now(timezone.utc)
    to_record = next_round(upcoming, now)
    for name, preds in upcoming_preds.items():
        rows = to_record.merge(preds[["match_id", "p_home", "p_draw", "p_away"]], on="match_id")
        added = record_forecasts(rows.assign(model=name), season_label(season), now)
        print(f"Prediction record: {added} new {MODELS[name]} forecasts saved")

    predictions = {name: pd.concat([played_preds[name], upcoming_preds.get(name)]) for name in MODELS}
    content = build_site_data(matches, fixtures, schedule, predictions)
    content["backtest"] = backtest_summary(matches, played_preds)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        (out_dir / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote site data to {out_dir}")


if __name__ == "__main__":
    write_site_data()
