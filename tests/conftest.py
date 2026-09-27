"""Shared test helpers: a small made-up league so tests run offline and fast."""

from itertools import permutations

import numpy as np
import pandas as pd
import pytest

TEAMS_BY_SEASON = {
    0: ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"],
    1: ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Eta"],  # Zeta relegated, Eta promoted
    2: ["Alpha", "Beta", "Gamma", "Delta", "Eta", "Theta"],
    3: ["Alpha", "Beta", "Gamma", "Delta", "Eta", "Theta"],
}
STRENGTH = {"Alpha": 1.0, "Beta": 0.6, "Gamma": 0.3, "Delta": 0.0, "Epsilon": -0.3, "Zeta": -0.6, "Eta": -0.4, "Theta": -0.2}


def result_from_goals(home_goals, away_goals) -> np.ndarray:
    return np.where(home_goals > away_goals, "H", np.where(home_goals < away_goals, "A", "D"))


def make_league(seed: int = 0) -> pd.DataFrame:
    """Four short seasons; every pair plays home and away, two matches per date."""
    rng = np.random.default_rng(seed)
    rows = []
    for season, teams in TEAMS_BY_SEASON.items():
        date = pd.Timestamp(f"{2000 + season}-08-20")
        for i, (home, away) in enumerate(permutations(teams, 2)):
            if i % 2 == 0:
                date += pd.Timedelta(days=3)
            rows.append({
                "match_id": f"{date:%Y-%m-%d}_{home}_{away}", "season": season, "date": date,
                "home_team": home, "away_team": away,
                "home_goals": rng.poisson(np.exp(0.3 + STRENGTH[home] - STRENGTH[away])),
                "away_goals": rng.poisson(np.exp(0.0 + STRENGTH[away] - STRENGTH[home])),
            })  # fmt: skip
    df = pd.DataFrame(rows)
    df["result"] = result_from_goals(df["home_goals"], df["away_goals"])
    return df


def scramble_from(matches: pd.DataFrame, cut: pd.Timestamp, seed: int = 99) -> pd.DataFrame:
    """Replace every result on or after `cut` with random scores."""
    rng = np.random.default_rng(seed)
    out = matches.copy()
    later = out["date"] >= cut
    out.loc[later, "home_goals"] = rng.integers(0, 6, later.sum())
    out.loc[later, "away_goals"] = rng.integers(0, 6, later.sum())
    out["result"] = result_from_goals(out["home_goals"], out["away_goals"])
    return out


def assert_no_lookahead(predict, matches: pd.DataFrame, cuts: list[pd.Timestamp]) -> None:
    """Fail if any prediction for a match on or before `cut` changes when results from `cut` on are altered.

    `predict(matches)` must return a DataFrame with match_id, date, p_home, p_draw, p_away.
    """
    baseline = predict(matches).set_index("match_id")
    for cut in cuts:
        altered = predict(scramble_from(matches, cut)).set_index("match_id")
        probs = ["p_home", "p_draw", "p_away"]
        up_to_cut = baseline.index[baseline["date"] <= cut]
        assert len(up_to_cut) > 0
        np.testing.assert_allclose(
            altered.loc[up_to_cut, probs], baseline.loc[up_to_cut, probs], rtol=0, atol=1e-12,
            err_msg=f"Predictions up to {cut.date()} changed when later results changed: look-ahead!",
        )  # fmt: skip
        # Sanity check that the test has teeth: later predictions *should* change
        after = baseline.index[baseline["date"] > cut]
        if len(after):
            assert not np.allclose(altered.loc[after, probs], baseline.loc[after, probs])


@pytest.fixture
def league() -> pd.DataFrame:
    return make_league()
