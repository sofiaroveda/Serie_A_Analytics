"""Elo ratings for Serie A teams, and home/draw/away probabilities from them.

How it works:
1. Every team has a rating. Before a match, the rating gap (plus a home
   advantage bonus) gives the home side's expected score between 0 and 1.
2. After the match, both ratings move by K x (actual score - expected score),
   scaled up for bigger winning margins. What one team gains, the other loses.
3. Between seasons, ratings are pulled part of the way back to the average,
   and promoted teams start below average.
4. An ordered logistic model, fitted only on earlier seasons, turns the rating
   gap into probabilities of a home win, draw and away win.

Run `python -m pipeline.elo` to tune the settings on the tuning seasons and
print a walk-forward backtest against the market on the test seasons.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from pipeline.evaluate import OUTCOME_INDEX, TEST_SEASONS, TUNING_SEASONS, WARMUP_SEASONS, rps

MEAN_RATING = 1500.0


@dataclass(frozen=True)
class EloParams:
    """Settings of the Elo model.

    Defaults were chosen by `tune` on the 2008/09-2013/14 seasons (mean RPS 0.2004).
    Home advantage came out at 0 in the rating updates, but the scores were almost
    identical for 0-80 (RPS within 0.00003): the outcome model already learns how
    much playing at home is worth, so this setting barely matters.
    """

    k: float = 10.0  # how fast ratings react to results
    home_advantage: float = 0.0  # rating points added to the home side in the updates
    season_regression: float = 0.3  # fraction of the way back to average between seasons
    promoted_gap: float = 50.0  # promoted teams start this far below average


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------


def expected_home_score(home_rating: float, away_rating: float, home_advantage: float) -> float:
    """Home side's expected score (win = 1, draw = 0.5, loss = 0) from the rating gap."""
    return 1 / (1 + 10 ** ((away_rating - home_rating - home_advantage) / 400))


def goal_diff_multiplier(goal_diff: int) -> float:
    """Bigger wins move ratings more (the rule used by the World Football Elo Ratings)."""
    margin = abs(goal_diff)
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11 + margin) / 8


def start_new_season(ratings: dict[str, float], teams: set[str], params: EloParams) -> dict[str, float]:
    """Ratings for a new season's teams.

    Teams from last season are pulled part of the way back to the average;
    everyone else (promoted clubs) starts `promoted_gap` below it. Ratings are
    then shifted so the league average stays at MEAN_RATING.
    """
    new = {}
    for team in teams:
        if team in ratings:
            new[team] = MEAN_RATING + (1 - params.season_regression) * (ratings[team] - MEAN_RATING)
        else:
            new[team] = MEAN_RATING - params.promoted_gap
    shift = MEAN_RATING - np.mean(list(new.values()))
    return {team: rating + shift for team, rating in new.items()}


def run_elo(matches: pd.DataFrame, params: EloParams) -> tuple[pd.DataFrame, dict[str, float]]:
    """Go through all matches in date order and record each team's rating before each match.

    Every match on a given date is rated with the ratings from before that date,
    and only then are the ratings updated, so a match's pre-match ratings never
    depend on results from its own date or later.

    Returns a table (match_id, elo_home, elo_away) and the ratings after the last match.
    """
    m = matches.sort_values(["date", "match_id"]).reset_index(drop=True)
    home, away = m["home_team"].to_numpy(), m["away_team"].to_numpy()
    goal_diff = (m["home_goals"] - m["away_goals"]).to_numpy()
    seasons, dates = m["season"].to_numpy(), m["date"].to_numpy()
    teams_by_season = {s: set(g["home_team"]) | set(g["away_team"]) for s, g in m.groupby("season")}

    pre_home, pre_away = np.empty(len(m)), np.empty(len(m))
    day_starts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1]])
    day_ends = np.r_[day_starts[1:], len(m)]

    ratings: dict[str, float] = {}
    season = None
    for start, end in zip(day_starts, day_ends):
        if seasons[start] != season:
            season = seasons[start]
            ratings = start_new_season(ratings, teams_by_season[season], params)

        # 1) record everyone's rating before today's matches
        for i in range(start, end):
            pre_home[i], pre_away[i] = ratings[home[i]], ratings[away[i]]
        # 2) then update with today's results
        for i in range(start, end):
            expected = expected_home_score(pre_home[i], pre_away[i], params.home_advantage)
            actual = 1.0 if goal_diff[i] > 0 else 0.5 if goal_diff[i] == 0 else 0.0
            change = params.k * goal_diff_multiplier(goal_diff[i]) * (actual - expected)
            ratings[home[i]] += change
            ratings[away[i]] -= change

    history = pd.DataFrame({"match_id": m["match_id"], "elo_home": pre_home, "elo_away": pre_away})
    return history, ratings


# ---------------------------------------------------------------------------
# From rating gap to home / draw / away probabilities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutcomeModel:
    """Ordered logistic model: P(result) from the rating gap.

    Think of a hidden "how well the home side did" score = slope x gap + noise.
    Below `draw_low` it's an away win, above `draw_high` a home win, in between a draw.
    """

    slope: float
    draw_low: float
    draw_high: float

    def probabilities(self, rating_gap: np.ndarray) -> np.ndarray:
        """(n, 3) array of home, draw, away probabilities. `rating_gap` includes home advantage."""
        x = self.slope * np.asarray(rating_gap, dtype=float) / 400
        p_away = expit(self.draw_low - x)
        p_away_or_draw = expit(self.draw_high - x)
        return np.column_stack([1 - p_away_or_draw, p_away_or_draw - p_away, p_away])


def fit_outcome_model(rating_gap: np.ndarray, results) -> OutcomeModel:
    """Fit the ordered logistic model by maximum likelihood."""
    outcome = np.array([OUTCOME_INDEX[r] for r in results])
    rows = np.arange(len(outcome))

    def negative_log_likelihood(theta: np.ndarray) -> float:
        slope, draw_low, log_width = theta
        model = OutcomeModel(slope, draw_low, draw_low + np.exp(log_width))  # keeps draw_high > draw_low
        p = model.probabilities(rating_gap)[rows, outcome]
        return -np.sum(np.log(np.clip(p, 1e-12, 1)))

    fit = minimize(negative_log_likelihood, x0=np.array([2.0, -1.0, 0.0]), method="Nelder-Mead",
                   options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 2000})  # fmt: skip
    slope, draw_low, log_width = fit.x
    return OutcomeModel(slope, draw_low, draw_low + np.exp(log_width))


# ---------------------------------------------------------------------------
# Walk-forward predictions
# ---------------------------------------------------------------------------


def predict_matches(matches: pd.DataFrame, params: EloParams, first_season: int) -> pd.DataFrame:
    """Walk-forward probabilities for every match from `first_season` on.

    Ratings only use earlier dates (see run_elo), and the outcome model for each
    season is fitted only on earlier seasons.
    """
    history, _ = run_elo(matches, params)
    df = matches[["match_id", "season", "date", "home_team", "away_team", "result"]].merge(history, on="match_id")
    df["rating_gap"] = df["elo_home"] + params.home_advantage - df["elo_away"]

    predicted = []
    for season in sorted(s for s in df["season"].unique() if s >= first_season):
        train = df[df["season"] < season]
        model = fit_outcome_model(train["rating_gap"].to_numpy(), train["result"])
        this = df[df["season"] == season].copy()
        this[["p_home", "p_draw", "p_away"]] = model.probabilities(this["rating_gap"].to_numpy())
        predicted.append(this)
    return pd.concat(predicted, ignore_index=True).sort_values(["date", "match_id"]).reset_index(drop=True)


def predict_fixtures(matches: pd.DataFrame, fixtures: pd.DataFrame, params: EloParams, season: int) -> pd.DataFrame:
    """Probabilities for upcoming `fixtures` in `season`, using every result played so far."""
    _, ratings = run_elo(matches, params)
    if season not in set(matches["season"]):  # the new season hasn't started yet
        ratings = start_new_season(ratings, set(fixtures["home_team"]) | set(fixtures["away_team"]), params)

    train = run_elo(matches[matches["season"] < season], params)[0].merge(matches, on="match_id")
    model = fit_outcome_model(
        (train["elo_home"] + params.home_advantage - train["elo_away"]).to_numpy(), train["result"]
    )
    out = fixtures[["match_id", "date", "home_team", "away_team"]].copy()
    out["elo_home"] = out["home_team"].map(ratings)
    out["elo_away"] = out["away_team"].map(ratings)
    out["rating_gap"] = out["elo_home"] + params.home_advantage - out["elo_away"]
    out[["p_home", "p_draw", "p_away"]] = model.probabilities(out["rating_gap"].to_numpy())
    return out


# ---------------------------------------------------------------------------
# Tuning (on the tuning seasons only)
# ---------------------------------------------------------------------------

DEFAULT_GRID = {
    "k": [4, 6, 8, 10, 12, 15, 20],
    "home_advantage": [0, 20, 40, 60, 80],
    "season_regression": [0.1, 0.2, 0.3, 0.4, 0.5],
    "promoted_gap": [0, 25, 50, 75, 100],
}


def tune(matches: pd.DataFrame, seasons=TUNING_SEASONS, grid: dict[str, list] = DEFAULT_GRID) -> pd.DataFrame:
    """Try every combination in `grid` and score each by mean RPS on `seasons`.

    Matches after the last tuning season are dropped first, so the test
    seasons can't influence the choice.
    """
    seasons = list(seasons)
    data = matches[matches["season"] <= max(seasons)]
    rows = []
    for values in product(*grid.values()):
        params = EloParams(**dict(zip(grid.keys(), values)))
        preds = predict_matches(data, params, first_season=min(seasons))
        rows.append({**asdict(params), "rps": rps(preds[["p_home", "p_draw", "p_away"]].to_numpy(), preds["result"])})
    return pd.DataFrame(rows).sort_values("rps").reset_index(drop=True)


def main() -> None:
    from pipeline.data import PROCESSED_DIR
    from pipeline.evaluate import compare_with_market

    matches = pd.read_csv(PROCESSED_DIR / "matches.csv", parse_dates=["date"])
    print(f"Tuning on {min(TUNING_SEASONS)}-{max(TUNING_SEASONS)} "
          f"(warm-up {min(WARMUP_SEASONS)}-{max(WARMUP_SEASONS)})...")  # fmt: skip
    results = tune(matches)
    print(results.head(10).to_string(index=False))

    best = EloParams(**results.iloc[0].drop("rps").to_dict())
    print(f"\nBest: {best}\n\nWalk-forward test on {min(TEST_SEASONS)}-{max(TEST_SEASONS)}:")
    preds = predict_matches(matches, best, first_season=min(TEST_SEASONS))
    preds = preds[preds["season"].isin(TEST_SEASONS)]
    table = compare_with_market(preds, matches, "Elo", markets={"Pinnacle closing": "pin_close"})
    print(table.pivot(index="season", columns="forecaster", values="rps").round(4).to_string())
    print(table[table["season"] == "All"].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
