"""Checks run before anything is published. Any problem stops the automated update.

    python -m pipeline.check                  # check the site data
    python -m pipeline.check --since HEAD     # ...and that no past prediction changed since HEAD
    python -m pipeline.check --ledger-only --since <commit>

The prediction record check compares every forecast file as it was at a git
commit with the files now: every earlier entry must still be there, unchanged.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pipeline.data import ROOT
from pipeline.export import MODELS, SITE_DATA_DIR
from pipeline.ledger import LEDGER_DIR

PROBABILITY_SETS = ["p", *MODELS]  # bookmakers ("p_home", ...) and each model ("elo_home", ...)


# ---------------------------------------------------------------------------
# Site data
# ---------------------------------------------------------------------------


def check_matches(matches: list[dict], matchdays: int) -> list[str]:
    """The season's match list: complete, one per pairing, sensible probabilities."""
    errors = []
    expected = matchdays * 10
    if len(matches) != expected:
        errors.append(f"matches.json has {len(matches)} matches, expected {expected}")
    per_matchday = {}
    for m in matches:
        per_matchday[m["matchday"]] = per_matchday.get(m["matchday"], 0) + 1
    wrong = {md: n for md, n in per_matchday.items() if n != 10}
    if wrong:
        errors.append(f"Matchdays without exactly 10 matches: {wrong}")
    if len({(m["home_team"], m["away_team"]) for m in matches}) != len(matches):
        errors.append("A home/away pairing appears twice in matches.json")

    for m in matches:
        if m["status"] == "played" and (m["home_goals"] is None or m["result"] not in ("H", "D", "A")):
            errors.append(f"{m['match_id']}: played but missing a score or result")
        for prefix in PROBABILITY_SETS:
            probs = [m.get(f"{prefix}_{o}") for o in ("home", "draw", "away")]
            if all(p is None for p in probs):
                continue
            if any(p is None or not 0 <= p <= 1 for p in probs) or abs(sum(probs) - 1) > 0.01:
                errors.append(f"{m['match_id']}: {prefix} probabilities don't add up to 1: {probs}")
        if m["status"] == "played" and m.get("dc_home") is None:
            errors.append(f"{m['match_id']}: played match has no model prediction")
    return errors


def check_table(table: list[dict], matches: list[dict]) -> list[str]:
    """The league table agrees with the results."""
    errors = []
    teams = {m["home_team"] for m in matches} | {m["away_team"] for m in matches}
    played = [m for m in matches if m["status"] == "played"]
    if played and {row["team"] for row in table} != teams:
        errors.append("The table's teams don't match the fixture list")
    for row in table:
        if row["points"] != 3 * row["won"] + row["drawn"]:
            errors.append(f"{row['team']}: points don't equal 3 x wins + draws")
        if row["played"] != row["won"] + row["drawn"] + row["lost"]:
            errors.append(f"{row['team']}: played doesn't equal wins + draws + losses")
    if sum(row["played"] for row in table) != 2 * len(played):
        errors.append("Total games in the table doesn't match the number of played matches")
    return errors


def check_simulation(simulation: dict) -> list[str]:
    """Simulated chances are valid probabilities and add up (1 champion, 4 top-4 places, 3 relegated)."""
    teams = simulation["teams"]
    errors = []
    for field, total in (("p_title", 1), ("p_top4", 4), ("p_relegation", 3)):
        if abs(sum(t[field] for t in teams) - total) > 0.01:
            errors.append(f"simulation: {field} adds up to {sum(t[field] for t in teams):.3f}, expected {total}")
    for t in teams:
        if not 0 <= t["p_title"] <= t["p_top4"] <= t["p_europe"] <= 1:
            errors.append(f"simulation: {t['team']} has inconsistent chances")
        if abs(sum(t["positions"]) - 1) > 0.01:
            errors.append(f"simulation: {t['team']}'s position chances don't add up to 1")
    return errors


def check_site_data(data_dir: Path = SITE_DATA_DIR) -> list[str]:
    try:
        load = lambda name: json.loads((data_dir / f"{name}.json").read_text())  # noqa: E731
        summary, matches, table = load("summary"), load("matches"), load("table")
        simulation = load("simulation")
        load("backtest"), load("ratings")
    except (OSError, json.JSONDecodeError) as error:
        return [f"Could not read the site data: {error}"]
    return check_matches(matches, summary["matchdays"]) + check_table(table, matches) + check_simulation(simulation)


# ---------------------------------------------------------------------------
# Prediction record: append-only
# ---------------------------------------------------------------------------


def compare_ledgers(old: dict, new: dict | None, name: str) -> list[str]:
    """Every forecast in `old` must still be in `new`, exactly as it was."""
    if new is None:
        return [f"{name}: prediction file was deleted"]
    current = {(f["match_id"], f["model"]): f for f in new["forecasts"]}
    errors = []
    for entry in old["forecasts"]:
        key = (entry["match_id"], entry["model"])
        if key not in current:
            errors.append(f"{name}: forecast {key} was removed")
        elif current[key] != entry:
            errors.append(f"{name}: forecast {key} was changed")
    return errors


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def check_ledger_since(ref: str, ledger_dir: Path = LEDGER_DIR) -> list[str]:
    """Compare each prediction file at git commit `ref` with the file now."""
    relative = ledger_dir.relative_to(ROOT).as_posix()
    errors = []
    for path in _git("ls-tree", "-r", "--name-only", ref, "--", relative).split():
        old = json.loads(_git("show", f"{ref}:{path}"))
        now = ROOT / path
        new = json.loads(now.read_text()) if now.exists() else None
        errors += compare_ledgers(old, new, path)
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", help="git commit to compare the prediction record against")
    parser.add_argument("--ledger-only", action="store_true", help="only check the prediction record")
    args = parser.parse_args()

    errors = [] if args.ledger_only else check_site_data()
    if args.since:
        errors += check_ledger_since(args.since)
    if errors:
        print("CHECKS FAILED, nothing should be published:", *errors, sep="\n  - ")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
