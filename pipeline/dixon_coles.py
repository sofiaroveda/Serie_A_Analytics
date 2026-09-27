"""Dixon-Coles model: goals-based forecasts with attack and defence strengths.

How it works:
1. Home goals ~ Poisson(lambda) and away goals ~ Poisson(mu), where
       log lambda = intercept + home_advantage + attack[home] + defence[away]
       log mu     = intercept + attack[away] + defence[home]
   A high attack means a team scores a lot; a high defence value means it
   concedes a lot. Both are centred so that the average team is 0.
2. A correction factor tau (with parameter rho) adjusts the four low scores
   0-0, 1-0, 0-1 and 1-1, which a plain Poisson model gets slightly wrong.
3. Parameters are fitted by weighted maximum likelihood. Each match's weight
   halves every `half_life_days`, so recent form counts more.
4. A mild penalty pulls each team towards a prior: average for established
   teams, weaker than average for promoted teams (who have little Serie A data).
5. From lambda, mu and rho we get the probability of every scoreline, and from
   that home/draw/away, over/under 2.5 goals and both teams to score.

Run `python -m pipeline.dixon_coles` to tune on the tuning seasons and backtest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

from pipeline.evaluate import TEST_SEASONS, TUNING_SEASONS, rps

MAX_GOALS = 10  # score matrix covers 0-0 up to 10-10


@dataclass(frozen=True)
class DCParams:
    """Settings of the Dixon-Coles model.

    Defaults were chosen by `tune` on 2008/09-2013/14 (mean RPS 0.2008). The
    promoted-team prior barely matters (0.15 and 0.30 differ by 0.000001).
    """

    half_life_days: float = 270.0  # a match's weight halves every this many days
    promoted_prior: float = 0.3  # promoted teams' prior: attack -x, defence +x (log-goals)
    ridge: float = 2.0  # strength of the pull towards each team's prior
    window_days: int = 4 * 365  # ignore matches older than this


@dataclass(frozen=True)
class DCFit:
    """A fitted model: one attack and defence value per team, plus shared parameters."""

    teams: tuple[str, ...]
    attack: np.ndarray
    defence: np.ndarray
    intercept: float
    home_advantage: float
    rho: float

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        """(lambda, mu): expected home and away goals."""
        index = {team: i for i, team in enumerate(self.teams)}
        h, a = index[home_team], index[away_team]
        lam = np.exp(self.intercept + self.home_advantage + self.attack[h] + self.defence[a])
        mu = np.exp(self.intercept + self.attack[a] + self.defence[h])
        return float(lam), float(mu)


# ---------------------------------------------------------------------------
# Scorelines and derived probabilities
# ---------------------------------------------------------------------------


def score_matrix(lam: float, mu: float, rho: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    """P(home goals = i, away goals = j) for i, j in 0..max_goals, with the low-score correction."""
    goals = np.arange(max_goals + 1)
    matrix = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu))
    matrix[0, 0] *= 1 - lam * mu * rho
    matrix[0, 1] *= 1 + lam * rho
    matrix[1, 0] *= 1 + mu * rho
    matrix[1, 1] *= 1 - rho
    return matrix / matrix.sum()  # renormalise (tiny mass beyond max_goals is dropped)


def outcome_probabilities(matrix: np.ndarray) -> dict[str, float]:
    """Home/draw/away, over 2.5 goals and both-teams-to-score from a score matrix."""
    i, j = np.indices(matrix.shape)
    return {
        "p_home": float(matrix[i > j].sum()),
        "p_draw": float(np.trace(matrix)),
        "p_away": float(matrix[i < j].sum()),
        "p_over_2_5": float(matrix[i + j > 2.5].sum()),
        "p_btts": float(matrix[1:, 1:].sum()),
    }


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def _negative_log_likelihood(theta, home_idx, away_idx, x, y, w, prior_att, prior_def, ridge):
    """Weighted negative log-likelihood + penalty, and its exact gradient (for fast fitting)."""
    n = len(prior_att)
    raw_att, raw_def = theta[:n], theta[n : 2 * n]
    intercept, home_adv, rho = theta[2 * n :]
    att, dfn = raw_att - raw_att.mean(), raw_def - raw_def.mean()  # centre: average team = 0

    log_lam = intercept + home_adv + att[home_idx] + dfn[away_idx]
    log_mu = intercept + att[away_idx] + dfn[home_idx]
    lam, mu = np.exp(log_lam), np.exp(log_mu)

    # Low-score correction tau and the derivatives of log(tau)
    tau = np.ones_like(lam)
    dlogtau_dloglam, dlogtau_dlogmu, dlogtau_drho = np.zeros_like(lam), np.zeros_like(lam), np.zeros_like(lam)
    m00, m01 = (x == 0) & (y == 0), (x == 0) & (y == 1)
    m10, m11 = (x == 1) & (y == 0), (x == 1) & (y == 1)
    tau[m00] = 1 - lam[m00] * mu[m00] * rho
    tau[m01] = 1 + lam[m01] * rho
    tau[m10] = 1 + mu[m10] * rho
    tau[m11] = 1 - rho
    tau = np.maximum(tau, 1e-10)
    dlogtau_dloglam[m00] = -lam[m00] * mu[m00] * rho / tau[m00]
    dlogtau_dlogmu[m00] = -lam[m00] * mu[m00] * rho / tau[m00]
    dlogtau_drho[m00] = -lam[m00] * mu[m00] / tau[m00]
    dlogtau_dloglam[m01] = lam[m01] * rho / tau[m01]
    dlogtau_drho[m01] = lam[m01] / tau[m01]
    dlogtau_dlogmu[m10] = mu[m10] * rho / tau[m10]
    dlogtau_drho[m10] = mu[m10] / tau[m10]
    dlogtau_drho[m11] = -1 / tau[m11]

    # Poisson log-likelihood (the constant log(x!) terms are dropped)
    log_lik = np.sum(w * (np.log(tau) + x * log_lam - lam + y * log_mu - mu))
    penalty = ridge * (np.sum((att - prior_att) ** 2) + np.sum((dfn - prior_def) ** 2))

    g_loglam = w * (x - lam + dlogtau_dloglam)
    g_logmu = w * (y - mu + dlogtau_dlogmu)
    g_att = np.bincount(home_idx, g_loglam, n) + np.bincount(away_idx, g_logmu, n) - 2 * ridge * (att - prior_att)
    g_def = np.bincount(away_idx, g_loglam, n) + np.bincount(home_idx, g_logmu, n) - 2 * ridge * (dfn - prior_def)
    grad = np.concatenate([
        g_att - g_att.mean(),  # chain rule through the centring
        g_def - g_def.mean(),
        [g_loglam.sum() + g_logmu.sum(), g_loglam.sum(), np.sum(w * dlogtau_drho)],
    ])  # fmt: skip
    return -(log_lik - penalty), -grad


def fit(
    train: pd.DataFrame,
    as_of: pd.Timestamp,
    params: DCParams,
    promoted: set[str] = frozenset(),
    extra_teams: set[str] = frozenset(),
    start: DCFit | None = None,
) -> DCFit:
    """Fit the model on `train` (matches before `as_of`), weighting recent matches more.

    `promoted` teams get a weaker-than-average prior. `extra_teams` are teams
    to include even with no matches in `train` (e.g. this season's promoted
    clubs). `start` is a previous fit to start the optimiser from (faster).
    """
    teams = tuple(sorted(set(train["home_team"]) | set(train["away_team"]) | set(extra_teams)))
    index = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    home_idx = train["home_team"].map(index).to_numpy()
    away_idx = train["away_team"].map(index).to_numpy()
    days_ago = (as_of - train["date"]).dt.days.to_numpy()
    w = 0.5 ** (days_ago / params.half_life_days)

    is_promoted = np.array([team in promoted for team in teams])
    prior_att = np.where(is_promoted, -params.promoted_prior, 0.0)
    prior_def = np.where(is_promoted, params.promoted_prior, 0.0)

    theta0 = np.concatenate([prior_att, prior_def, [0.3, 0.25, -0.05]])
    if start is not None:  # warm start from the previous fit where teams overlap
        old = {team: i for i, team in enumerate(start.teams)}
        for team, i in index.items():
            if team in old:
                theta0[i], theta0[n + i] = start.attack[old[team]], start.defence[old[team]]
        theta0[2 * n :] = [start.intercept, start.home_advantage, start.rho]

    bounds = [(None, None)] * (2 * n + 2) + [(-0.3, 0.3)]
    result = minimize(
        _negative_log_likelihood, theta0, jac=True, method="L-BFGS-B", bounds=bounds,
        args=(home_idx, away_idx, train["home_goals"].to_numpy(), train["away_goals"].to_numpy(),
              w, prior_att, prior_def, params.ridge),
    )  # fmt: skip
    theta = result.x
    att, dfn = theta[:n] - theta[:n].mean(), theta[n : 2 * n] - theta[n : 2 * n].mean()
    return DCFit(teams, att, dfn, float(theta[2 * n]), float(theta[2 * n + 1]), float(theta[2 * n + 2]))


# ---------------------------------------------------------------------------
# Walk-forward predictions
# ---------------------------------------------------------------------------


def _predict_rows(model: DCFit, rows: pd.DataFrame) -> list[dict]:
    out = []
    for row in rows.itertuples():
        lam, mu = model.expected_goals(row.home_team, row.away_team)
        out.append({"match_id": row.match_id, "exp_home_goals": lam, "exp_away_goals": mu, "rho": model.rho,
                    **outcome_probabilities(score_matrix(lam, mu, model.rho))})  # fmt: skip
    return out


def _promoted(matches: pd.DataFrame, season: int) -> tuple[set[str], set[str]]:
    """(this season's teams, those who weren't in last season's league)."""
    teams = set(matches.loc[matches["season"] == season, ["home_team", "away_team"]].stack())
    previous = set(matches.loc[matches["season"] == season - 1, ["home_team", "away_team"]].stack())
    return teams, teams - previous


def predict_matches(matches: pd.DataFrame, params: DCParams, first_season: int) -> pd.DataFrame:
    """Walk-forward forecasts from `first_season` on, refitting before every match date.

    Each fit uses only matches strictly before that date (and within the window).
    """
    matches = matches.sort_values(["date", "match_id"]).reset_index(drop=True)
    predictions, model = [], None
    for date, today in matches[matches["season"] >= first_season].groupby("date", sort=True):
        season = int(today["season"].iloc[0])
        season_teams, promoted = _promoted(matches, season)
        train = matches[(matches["date"] < date) & (matches["date"] >= date - pd.Timedelta(days=params.window_days))]
        model = fit(train, date, params, promoted, season_teams, start=model)
        predictions.extend(_predict_rows(model, today))
    preds = pd.DataFrame(predictions)
    return matches[["match_id", "season", "date", "home_team", "away_team", "result"]].merge(preds, on="match_id")


def predict_fixtures(matches: pd.DataFrame, fixtures: pd.DataFrame, params: DCParams, season: int) -> pd.DataFrame:
    """Forecasts for upcoming `fixtures` in `season`, fitted on every result so far."""
    as_of = max(matches["date"].max() + pd.Timedelta(days=1), fixtures["date"].min())
    season_teams = set(fixtures[["home_team", "away_team"]].stack()) | set(
        matches.loc[matches["season"] == season, ["home_team", "away_team"]].stack()
    )
    previous = set(matches.loc[matches["season"] == season - 1, ["home_team", "away_team"]].stack())
    train = matches[matches["date"] >= as_of - pd.Timedelta(days=params.window_days)]
    model = fit(train, as_of, params, season_teams - previous, season_teams)
    preds = pd.DataFrame(_predict_rows(model, fixtures))
    return fixtures[["match_id", "date", "home_team", "away_team"]].merge(preds, on="match_id")


# ---------------------------------------------------------------------------
# Tuning (on the tuning seasons only)
# ---------------------------------------------------------------------------

DEFAULT_GRID = {
    "half_life_days": [120, 180, 270, 365, 540, 730],
    "promoted_prior": [0.0, 0.15, 0.3],
}


def tune(matches: pd.DataFrame, seasons=TUNING_SEASONS, grid: dict[str, list] = DEFAULT_GRID) -> pd.DataFrame:
    """Score every combination in `grid` by mean RPS on `seasons` (test seasons are dropped first)."""
    seasons = list(seasons)
    data = matches[matches["season"] <= max(seasons)]
    rows = []
    for values in product(*grid.values()):
        params = DCParams(**dict(zip(grid.keys(), values)))
        preds = predict_matches(data, params, first_season=min(seasons))
        rows.append({**asdict(params), "rps": rps(preds[["p_home", "p_draw", "p_away"]].to_numpy(), preds["result"])})
        print(f"  {values}: RPS {rows[-1]['rps']:.5f}", flush=True)
    return pd.DataFrame(rows).sort_values("rps").reset_index(drop=True)


def main() -> None:
    from pipeline.data import PROCESSED_DIR
    from pipeline.elo import EloParams
    from pipeline.elo import predict_matches as elo_predict
    from pipeline.evaluate import compare_with_market

    matches = pd.read_csv(PROCESSED_DIR / "matches.csv", parse_dates=["date"])
    print(f"Tuning on {min(TUNING_SEASONS)}-{max(TUNING_SEASONS)}...")
    results = tune(matches)
    print(results.to_string(index=False))

    best = DCParams(**results.iloc[0].drop("rps").to_dict())
    print(f"\nBest: {best}\n\nWalk-forward test on {min(TEST_SEASONS)}-{max(TEST_SEASONS)}:")
    dc = predict_matches(matches, best, first_season=min(TEST_SEASONS))
    dc = dc[dc["season"].isin(TEST_SEASONS)]
    elo = elo_predict(matches, EloParams(), first_season=min(TEST_SEASONS))
    elo = elo[elo["season"].isin(TEST_SEASONS)]

    # Score all three on the same matches: those with Pinnacle closing odds
    pinnacle = {"Pinnacle closing": "pin_close"}
    covered = matches.dropna(subset=["pin_close_h"])["match_id"]
    table = pd.concat([
        compare_with_market(dc, matches, "Dixon-Coles", markets=pinnacle),
        compare_with_market(elo[elo["match_id"].isin(covered)], matches, "Elo", markets={}),
    ])  # fmt: skip
    print(table.pivot(index="season", columns="forecaster", values="rps").round(4).to_string())
    print(table[table["season"] == "All"].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
