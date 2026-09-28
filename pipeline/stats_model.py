"""Predicting match stats: corners, yellow cards, shots and shots on target.

Each stat uses the same team-strength model as goals (pipeline/dixon_coles.py) without the
low-score correction: every team gets a "for" and an "against" rating (e.g. corners won and
corners conceded), learned from recent matches with time weighting, plus a home effect.
That gives the expected count for each side.

For "over / under" chances we need the spread around that expectation. Corners and shots
vary more than a Poisson count, so totals use a negative binomial whose extra spread
(`DISPERSION`, the "size" k: variance = mean + mean^2 / k) is measured on the tuning
seasons; when a stat varies less than Poisson (yellow cards) we use Poisson.

Run `python -m pipeline.stats_model` to tune on the tuning seasons, backtest on the test
seasons against a league-average baseline, and write site/data/stats_backtest.json.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from pipeline.dixon_coles import DCParams, _promoted, fit
from pipeline.evaluate import TEST_SEASONS, TUNING_SEASONS

# stat -> (home column, away column, over/under line, label)
STATS = {
    "corners": ("home_corners", "away_corners", 9.5, "Corners"),
    "yellow_cards": ("home_yellow", "away_yellow", 4.5, "Yellow cards"),
    "shots": ("home_shots", "away_shots", 24.5, "Shots"),
    "shots_on_target": ("home_on_target", "away_on_target", 8.5, "Shots on target"),
}
# Chosen by `tune` on 2008/09-2013/14 (see main; shots also checked at 60-120 days, all worse).
# Dispersion is the negative binomial "size" k; None = Poisson (cards vary less than Poisson).
HALF_LIFE = {"corners": 730, "yellow_cards": 365, "shots": 180, "shots_on_target": 365}
DISPERSION = {"corners": 59.2, "yellow_cards": None, "shots": 110.5, "shots_on_target": 64.6}
PROMOTED_PRIOR = 0.1  # promoted teams start slightly below average ("for") and above ("against")


def stat_params(stat: str, half_life: float | None = None) -> DCParams:
    return DCParams(half_life_days=half_life or HALF_LIFE[stat], promoted_prior=PROMOTED_PRIOR)


def as_counts(matches: pd.DataFrame, stat: str) -> pd.DataFrame:
    """The matches with this stat's columns renamed to home_goals / away_goals (what `fit` reads)."""
    home, away = STATS[stat][:2]
    counts = matches.drop(columns=["home_goals", "away_goals"]).rename(columns={home: "home_goals", away: "away_goals"})
    return counts.dropna(subset=["home_goals", "away_goals"])


def p_over(expected_total: float, line: float, dispersion: float | None) -> float:
    """Chance the total is above `line` (e.g. over 9.5 corners)."""
    threshold = math.floor(line)
    if dispersion is None:
        return float(poisson.sf(threshold, expected_total))
    return float(nbinom.sf(threshold, dispersion, dispersion / (dispersion + expected_total)))


def predict_matches(matches: pd.DataFrame, stat: str, first_season: int, half_life: float | None = None) -> pd.DataFrame:
    """Walk-forward expected counts (exp_home, exp_away) for every match from `first_season` on.

    Refitted before every match date using only earlier matches, like the goals model.
    """
    params = stat_params(stat, half_life)
    counts = as_counts(matches, stat).sort_values(["date", "match_id"])
    rows, model = [], None
    for date, today in matches[matches["season"] >= first_season].groupby("date", sort=True):
        season = int(today["season"].iloc[0])
        season_teams, promoted = _promoted(matches, season)
        train = counts[(counts["date"] < date) & (counts["date"] >= date - pd.Timedelta(days=params.window_days))]
        model = fit(train, date, params, promoted, season_teams, start=model, low_score_correction=False)
        for m in today.itertuples():
            lam, mu = model.expected_goals(m.home_team, m.away_team)
            rows.append({"match_id": m.match_id, "exp_home": lam, "exp_away": mu})
    return pd.DataFrame(rows)


def predict_fixtures(matches: pd.DataFrame, fixtures: pd.DataFrame, stat: str, season: int) -> pd.DataFrame:
    """Expected counts for upcoming `fixtures`, fitted on every match so far."""
    params = stat_params(stat)
    as_of = max(matches["date"].max() + pd.Timedelta(days=1), fixtures["date"].min())
    season_teams = set(fixtures[["home_team", "away_team"]].stack()) | set(
        matches.loc[matches["season"] == season, ["home_team", "away_team"]].stack()
    )
    previous = set(matches.loc[matches["season"] == season - 1, ["home_team", "away_team"]].stack())
    counts = as_counts(matches, stat)
    train = counts[counts["date"] >= as_of - pd.Timedelta(days=params.window_days)]
    model = fit(train, as_of, params, season_teams - previous, season_teams, low_score_correction=False)
    rows = []
    for m in fixtures.itertuples():
        lam, mu = model.expected_goals(m.home_team, m.away_team)
        rows.append({"match_id": m.match_id, "exp_home": lam, "exp_away": mu})
    return pd.DataFrame(rows)


def with_over(preds: pd.DataFrame, stat: str) -> pd.DataFrame:
    """Add the expected total and the chance of going over the stat's line."""
    line = STATS[stat][2]
    out = preds.copy()
    out["exp_total"] = out["exp_home"] + out["exp_away"]
    out["p_over"] = [p_over(t, line, DISPERSION[stat]) for t in out["exp_total"]]
    return out


# ---------------------------------------------------------------------------
# Tuning and backtest
# ---------------------------------------------------------------------------


def poisson_deviance(y: np.ndarray, m: np.ndarray) -> float:
    """Mean Poisson deviance: how badly expected counts `m` fit actual counts `y` (lower is better)."""
    y, m = np.asarray(y, float), np.asarray(m, float)
    term = np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / m), 0.0)
    return float(np.mean(2 * (term - (y - m))))


def _scored(matches: pd.DataFrame, preds: pd.DataFrame, stat: str) -> pd.DataFrame:
    home, away = STATS[stat][:2]
    return preds.merge(matches[["match_id", "season", home, away]], on="match_id").dropna(subset=[home, away])


def tune(matches: pd.DataFrame, stat: str, grid=(180, 365, 730, 1460)) -> dict:
    """Pick the half-life (by Poisson deviance) and the extra spread, on the tuning seasons only."""
    home, away = STATS[stat][:2]
    data = matches[matches["season"] <= max(TUNING_SEASONS)]
    results = {}
    for half_life in grid:
        s = _scored(data, predict_matches(data, stat, min(TUNING_SEASONS), half_life), stat)
        results[half_life] = (poisson_deviance(s[home], s["exp_home"]) + poisson_deviance(s[away], s["exp_away"])) / 2
        print(f"  {stat} half-life {half_life}: deviance {results[half_life]:.4f}", flush=True)
    best = min(results, key=results.get)

    # Extra spread of the total around its expectation: variance = m + m^2 / k
    s = _scored(data, predict_matches(data, stat, min(TUNING_SEASONS), best), stat)
    m, y = (s["exp_home"] + s["exp_away"]).to_numpy(), (s[home] + s[away]).to_numpy()
    excess = np.mean((y - m) ** 2) - np.mean(m)
    k = float(np.mean(m**2) / excess) if excess > 0 else None
    return {"half_life": best, "deviance": results, "dispersion": k}


def backtest(matches: pd.DataFrame, stat: str) -> dict:
    """Test seasons: our expected totals and over/under chances vs a league-average baseline."""
    home, away, line, label = STATS[stat]
    s = _scored(matches, with_over(predict_matches(matches, stat, min(TEST_SEASONS)), stat), stat)
    s = s[s["season"].isin(TEST_SEASONS)]
    actual = (s[home] + s[away]).to_numpy()
    over = (actual > line).astype(float)

    # Baseline: last season's league averages (home and away) and last season's over rate
    base_total, base_over = np.empty(len(s)), np.empty(len(s))
    for season in s["season"].unique():
        prev = matches[(matches["season"] == season - 1)].dropna(subset=[home, away])
        prev_total = prev[home] + prev[away]
        mask = (s["season"] == season).to_numpy()
        base_total[mask] = prev_total.mean()
        base_over[mask] = (prev_total > line).mean()

    return {
        "label": label, "line": line, "matches": int(len(s)),
        "mae_model": round(float(np.mean(np.abs(actual - s["exp_total"]))), 3),
        "mae_baseline": round(float(np.mean(np.abs(actual - base_total))), 3),
        "brier_model": round(float(np.mean((s["p_over"] - over) ** 2)), 4),
        "brier_baseline": round(float(np.mean((base_over - over) ** 2)), 4),
        "over_rate": round(float(over.mean()), 3),
        "hit_rate_model": round(float(np.mean((s["p_over"] > 0.5) == (over == 1))), 3),
    }  # fmt: skip


def main() -> None:
    from pipeline.data import PROCESSED_DIR, ROOT

    matches = pd.read_csv(PROCESSED_DIR / "matches.csv", parse_dates=["date"])
    results = {}
    for stat in STATS:
        tuned = tune(matches, stat)
        HALF_LIFE[stat], DISPERSION[stat] = tuned["half_life"], tuned["dispersion"]
        print(f"{stat}: half-life {tuned['half_life']}, dispersion {tuned['dispersion']}")
        results[stat] = {**backtest(matches, stat), "half_life": tuned["half_life"], "dispersion": tuned["dispersion"]}
        print(f"  test seasons: {results[stat]}")
    out = ROOT / "site" / "data" / "stats_backtest.json"
    out.write_text(json.dumps({"seasons": f"{min(TEST_SEASONS)}-{max(TEST_SEASONS)}", "stats": results}, indent=1) + "\n")
    print(f"Wrote {out}. Copy the half-lives and dispersions above into HALF_LIFE and DISPERSION.")


if __name__ == "__main__":
    main()
