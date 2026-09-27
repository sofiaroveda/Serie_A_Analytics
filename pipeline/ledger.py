"""The prediction record: forecasts saved before kick-off and never changed afterwards.

Each run adds forecasts for the next round of matches to
predictions/<season>/matchday-NN.json. Entries are append-only: once a
(match, model) forecast is written it is never modified, and nothing is
recorded for a match that has already kicked off. Git history then shows
when each forecast was published.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.data import ROOT

LEDGER_DIR = ROOT / "predictions"
ITALY = ZoneInfo("Europe/Rome")  # openfootball kick-off times are Italian local time


def kickoff_times(matches: pd.DataFrame) -> pd.Series:
    """Kick-off as a UTC timestamp. A missing time counts as midnight (the earliest possible)."""
    local = pd.to_datetime(matches["date"].dt.strftime("%Y-%m-%d") + " " + matches["time"].fillna("00:00"))
    return local.dt.tz_localize(ITALY).dt.tz_convert("UTC")


def next_round(upcoming: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Matches to record now: the matchday of the next kick-off, plus anything kicking off before it ends.

    Recording only the next round means forecasts are locked in after the
    previous round's results are known, not weeks in advance.
    """
    future = upcoming[kickoff_times(upcoming) > now]
    if future.empty:
        return future
    kickoffs = kickoff_times(future)
    matchday = future.loc[kickoffs.idxmin(), "matchday"]
    round_end = kickoffs[future["matchday"] == matchday].max()
    return future[(future["matchday"] == matchday) | (kickoffs <= round_end)]


def ledger_path(season_label: str, matchday: int, ledger_dir: Path = LEDGER_DIR) -> Path:
    return ledger_dir / season_label.replace("/", "-") / f"matchday-{matchday:02d}.json"


def record_forecasts(
    forecasts: pd.DataFrame, season_label: str, now: datetime, ledger_dir: Path = LEDGER_DIR
) -> int:
    """Append new forecasts to the ledger. Returns how many were added.

    `forecasts` has match_id, matchday, date, time, home_team, away_team, model,
    p_home, p_draw, p_away. Existing (match_id, model) entries are left exactly
    as they are, and matches that have already kicked off are skipped.
    """
    forecasts = forecasts[kickoff_times(forecasts) > now]
    added = 0
    for matchday, group in forecasts.groupby("matchday"):
        path = ledger_path(season_label, int(matchday), ledger_dir)
        ledger = json.loads(path.read_text()) if path.exists() else {
            "season": season_label, "matchday": int(matchday), "forecasts": [],
        }  # fmt: skip
        already = {(f["match_id"], f["model"]) for f in ledger["forecasts"]}
        before = len(ledger["forecasts"])
        for row in group.itertuples():
            if (row.match_id, row.model) in already:
                continue
            ledger["forecasts"].append({
                "match_id": row.match_id,
                "kickoff": f"{row.date:%Y-%m-%d} {row.time}",
                "home_team": row.home_team,
                "away_team": row.away_team,
                "model": row.model,
                "p_home": round(float(row.p_home), 4),
                "p_draw": round(float(row.p_draw), 4),
                "p_away": round(float(row.p_away), 4),
                "recorded_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
            })  # fmt: skip
        if len(ledger["forecasts"]) > before:
            added += len(ledger["forecasts"]) - before
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n")
    return added
