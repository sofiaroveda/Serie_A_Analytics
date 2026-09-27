"""Scoring rules for home/draw/away forecasts, and model-vs-market comparisons.

All scores are "lower is better". Probabilities are arrays of shape (n, 3) in
home, draw, away order; results are "H" / "D" / "A".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.market import implied_probabilities

# How the seasons are used (start years). Never tune on the test seasons.
WARMUP_SEASONS = range(2005, 2008)  # 2005/06-2007/08: ratings settle, nothing scored
TUNING_SEASONS = range(2008, 2014)  # 2008/09-2013/14: choose model settings here
TEST_SEASONS = range(2014, 2026)  # 2014/15-2025/26: honest out-of-sample test

OUTCOME_INDEX = {"H": 0, "D": 1, "A": 2}


def outcome_matrix(results: pd.Series | list[str]) -> np.ndarray:
    """One-hot matrix of what happened: "H" -> [1, 0, 0], "D" -> [0, 1, 0], "A" -> [0, 0, 1]."""
    index = np.array([OUTCOME_INDEX[r] for r in results])
    return np.eye(3)[index]


def rps(probs: np.ndarray, results) -> float:
    """Mean Ranked Probability Score, the standard score for football forecasts.

    It compares cumulative probabilities (home, then home-or-draw) with what
    happened, so predicting a draw when the home side wins is penalised less
    than predicting an away win.
    """
    outcomes = outcome_matrix(results)
    cum_diff = np.cumsum(probs, axis=1)[:, :2] - np.cumsum(outcomes, axis=1)[:, :2]
    return float(np.mean(np.sum(cum_diff**2, axis=1) / 2))


def log_loss(probs: np.ndarray, results) -> float:
    """Mean negative log of the probability given to what actually happened."""
    outcomes = outcome_matrix(results)
    p_happened = np.sum(probs * outcomes, axis=1)
    return float(-np.mean(np.log(np.clip(p_happened, 1e-15, 1))))


def brier(probs: np.ndarray, results) -> float:
    """Mean squared error between the probabilities and the one-hot outcome (summed over 3 outcomes)."""
    return float(np.mean(np.sum((probs - outcome_matrix(results)) ** 2, axis=1)))


def scores(probs: np.ndarray, results) -> dict[str, float]:
    return {"rps": rps(probs, results), "log_loss": log_loss(probs, results), "brier": brier(probs, results)}


def base_rate_forecast(matches: pd.DataFrame, target: pd.DataFrame) -> np.ndarray:
    """No-skill benchmark: for each target match, the home/draw/away frequencies of all earlier seasons."""
    seasons = target["season"].to_numpy()
    probs = np.empty((len(target), 3))
    for season in np.unique(seasons):
        earlier = matches.loc[matches["season"] < season, "result"]
        probs[seasons == season] = outcome_matrix(earlier).mean(axis=0)
    return probs


def compare_with_market(
    predictions: pd.DataFrame,
    matches: pd.DataFrame,
    model_name: str,
    markets: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Score a model and the market on exactly the same matches, per season and overall.

    `predictions` has match_id, p_home, p_draw, p_away. Only matches where the
    model and every market in `markets` (name -> odds column prefix) have
    probabilities are scored, so the comparison is like for like.
    """
    if markets is None:
        markets = {"Pinnacle closing": "pin_close", "Market avg closing": "avg_close"}
    df = matches.merge(predictions[["match_id", "p_home", "p_draw", "p_away"]], on="match_id")
    for prefix in markets.values():
        df = df.dropna(subset=[f"{prefix}_{o}" for o in "hda"])

    forecasters = {model_name: df[["p_home", "p_draw", "p_away"]].to_numpy()}
    for name, prefix in markets.items():
        forecasters[name] = implied_probabilities(df[[f"{prefix}_{o}" for o in "hda"]]).to_numpy()

    rows = []
    groups = [(season, df["season"] == season) for season in sorted(df["season"].unique())]
    groups.append(("All", pd.Series(True, index=df.index)))
    for label, mask in groups:
        for name, probs in forecasters.items():
            rows.append({"season": label, "forecaster": name, "matches": int(mask.sum()),
                         **scores(probs[mask.to_numpy()], df.loc[mask, "result"])})  # fmt: skip
    return pd.DataFrame(rows)
