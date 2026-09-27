"""Turn bookmaker odds into probabilities."""

from __future__ import annotations

import numpy as np
import pandas as pd


def implied_probabilities(odds: pd.DataFrame) -> pd.DataFrame:
    """Normalised home/draw/away probabilities from decimal odds (proportional method).

    `odds` has three columns in home, draw, away order. Raw implied probabilities
    (1 / odds) sum to slightly more than 1 because of the bookmaker's margin; we
    divide by that sum so they add up to exactly 1. Rows with missing odds give NaN.
    """
    raw = 1 / odds.to_numpy(dtype=float)
    probs = raw / raw.sum(axis=1, keepdims=True)
    return pd.DataFrame(probs, index=odds.index, columns=["home", "draw", "away"])


def overround(odds: pd.DataFrame) -> pd.Series:
    """Bookmaker margin: how much the raw implied probabilities exceed 1."""
    return pd.Series((1 / odds.to_numpy(dtype=float)).sum(axis=1) - 1, index=odds.index)


def best_available_probabilities(matches: pd.DataFrame, prefer: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """For each match, use the first odds source in `prefer` that has all three prices.

    `prefer` holds column prefixes such as ["pin_close", "avg_close"]. Returns the
    probabilities and a Series naming the source used for each row (NaN if none).
    """
    probs = pd.DataFrame(np.nan, index=matches.index, columns=["home", "draw", "away"])
    source = pd.Series(pd.NA, index=matches.index, dtype="object")
    for prefix in prefer:
        cols = [f"{prefix}_{o}" for o in ("h", "d", "a")]
        if not set(cols) <= set(matches.columns):
            continue
        todo = source.isna() & matches[cols].notna().all(axis=1)
        probs.loc[todo] = implied_probabilities(matches.loc[todo, cols]).to_numpy()
        source.loc[todo] = prefix
    return probs, source
