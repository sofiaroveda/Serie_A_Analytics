"""Monte Carlo simulation of the rest of the season.

Each remaining match gets a random scoreline drawn from the goals model's score
probabilities; points and goals are added to the current table; teams are ranked.
Repeating this many times gives each team's chance of every final position.

We are never sure exactly how strong a team is, and strength changes during a
season (form, injuries, transfers). So in each simulated season every team gets a
random strength shock (normal, standard deviation `strength_sd` in log-goals) that
lasts the whole simulated season. Without it the simulation is overconfident.
`strength_sd` is tuned on the tuning seasons with `calibrate_strength_sd`.

Teams level on points are ordered by Serie A's rules (pipeline/tiebreak.py), with a
two-team tie for the title or across the relegation line settled by a coin toss
standing in for the play-off. Simplification (stated on the site): the low-score
correction (rho) is left out of the simulation; it barely changes points.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.dixon_coles import DCParams, _predict_rows, fit_latest
from pipeline.evaluate import TUNING_SEASONS
from pipeline.tiebreak import order_teams

N_SIMS = 10_000
STRENGTH_SD = 0.10  # chosen by calibrate_strength_sd on 2008/09-2013/14 (Brier 0.0532 vs 0.0535 at 0)
CHAMPIONS_LEAGUE_PLACES = 4
EUROPE_PLACES = 6  # Champions League, Europa League and Conference League places
RELEGATION_PLACES = 3


def simulate_season(
    played: pd.DataFrame,
    remaining: pd.DataFrame,
    n_sims: int = N_SIMS,
    seed: int = 0,
    strength_sd: float = STRENGTH_SD,
) -> pd.DataFrame:
    """Chances of each final position for every team.

    `played` has home_team, away_team, home_goals, away_goals for matches already
    played. `remaining` has home_team, away_team, exp_home_goals and exp_away_goals
    (the goals model's forecast) for matches still to play.

    Returns one row per team with current and expected points, the chance of the
    title, top 4, Europe and relegation, and `position_probs` (chance of each place).
    """
    rng = np.random.default_rng(seed)
    teams = sorted(set(played[["home_team", "away_team"]].stack()) | set(remaining[["home_team", "away_team"]].stack()))
    index = {team: i for i, team in enumerate(teams)}
    n_teams = len(teams)

    # The table as it stands (the same in every simulated season)
    now_points, now_gf, now_ga = np.zeros(n_teams), np.zeros(n_teams), np.zeros(n_teams)
    for m in played.itertuples():
        h, a = index[m.home_team], index[m.away_team]
        now_gf[h] += m.home_goals
        now_ga[h] += m.away_goals
        now_gf[a] += m.away_goals
        now_ga[a] += m.home_goals
        now_points[h] += 3 if m.home_goals > m.away_goals else 1 if m.home_goals == m.away_goals else 0
        now_points[a] += 3 if m.away_goals > m.home_goals else 1 if m.home_goals == m.away_goals else 0

    # Play the rest of the season n_sims times: one row per simulated season, one column per team
    points = np.tile(now_points, (n_sims, 1))
    gf, ga = np.tile(now_gf, (n_sims, 1)), np.tile(now_ga, (n_sims, 1))
    # Each simulated season, every team is randomly a bit stronger or weaker than its rating
    shock = rng.normal(0.0, strength_sd, size=(n_sims, n_teams))
    sim_home_goals = np.zeros((n_sims, len(remaining)), dtype=int)  # kept for head-to-head tie-breaks
    sim_away_goals = np.zeros((n_sims, len(remaining)), dtype=int)
    for f, m in enumerate(remaining.itertuples()):
        h, a = index[m.home_team], index[m.away_team]
        home_goals = rng.poisson(m.exp_home_goals * np.exp(shock[:, h] - shock[:, a]))
        away_goals = rng.poisson(m.exp_away_goals * np.exp(shock[:, a] - shock[:, h]))
        sim_home_goals[:, f], sim_away_goals[:, f] = home_goals, away_goals
        gf[:, h] += home_goals
        ga[:, h] += away_goals
        gf[:, a] += away_goals
        ga[:, a] += home_goals
        points[:, h] += np.where(home_goals > away_goals, 3, np.where(home_goals == away_goals, 1, 0))
        points[:, a] += np.where(away_goals > home_goals, 3, np.where(home_goals == away_goals, 1, 0))

    # Rank each simulated table by Serie A's rules: points, head-to-head, goal difference,
    # goals scored, lots; a two-team tie for the title or across the relegation line is a play-off
    home_idx = np.concatenate([played["home_team"].map(index).to_numpy(), remaining["home_team"].map(index).to_numpy()]).astype(int)
    away_idx = np.concatenate([played["away_team"].map(index).to_numpy(), remaining["away_team"].map(index).to_numpy()]).astype(int)
    played_home_goals = played["home_goals"].to_numpy(dtype=float)
    played_away_goals = played["away_goals"].to_numpy(dtype=float)
    order = np.empty((n_sims, n_teams), dtype=int)
    for s in range(n_sims):
        order[s] = order_teams(
            points[s], gf[s] - ga[s], gf[s], home_idx, away_idx,
            np.concatenate([played_home_goals, sim_home_goals[s]]), np.concatenate([played_away_goals, sim_away_goals[s]]),
            rng=rng, playoffs=True,
        )  # fmt: skip
    positions = np.empty_like(order)
    rows = np.arange(n_sims)[:, None]
    positions[rows, order] = np.arange(n_teams)  # 0 = champions
    # position_probs[t, p] = share of seasons in which team t finishes in place p + 1
    position_probs = np.stack([(positions == p).mean(axis=0) for p in range(n_teams)], axis=1)

    games_played = np.zeros(n_teams)
    for column in ("home_team", "away_team"):
        for team, count in played[column].value_counts().items():
            games_played[index[team]] += count

    return pd.DataFrame({
        "team": teams,
        "played": games_played.astype(int),
        "points": now_points.astype(int),
        "exp_points": points.mean(axis=0),
        "exp_position": (positions + 1).mean(axis=0),
        "p_title": position_probs[:, 0],
        "p_top4": position_probs[:, :CHAMPIONS_LEAGUE_PLACES].sum(axis=1),
        "p_europe": position_probs[:, :EUROPE_PLACES].sum(axis=1),
        "p_relegation": position_probs[:, n_teams - RELEGATION_PLACES:].sum(axis=1),
        "position_probs": list(position_probs),
    }).sort_values(["exp_points", "p_title"], ascending=False).reset_index(drop=True)  # fmt: skip


# ---------------------------------------------------------------------------
# Tuning the strength uncertainty (on the tuning seasons only)
# ---------------------------------------------------------------------------

CHECKPOINTS = (50, 100, 190, 280)  # stop the season after this many matches and simulate the rest


def simulate_as_of(
    matches: pd.DataFrame,
    fixtures: pd.DataFrame,
    season: int,
    cutoff: pd.Timestamp,
    n_sims: int = N_SIMS,
    strength_sd: float = STRENGTH_SD,
    params: DCParams = DCParams(),
) -> pd.DataFrame:
    """Walk-forward simulation using only results from before `cutoff`.

    `fixtures` is the season's full fixture list (home_team, away_team). Matches of
    `season` played before `cutoff` count as results; every other fixture is
    simulated, with forecasts from the goals model fitted as of `cutoff`.
    """
    played = matches[(matches["season"] == season) & (matches["date"] < cutoff)]
    done = set(zip(played["home_team"], played["away_team"]))
    remaining = fixtures[[pair not in done for pair in zip(fixtures["home_team"], fixtures["away_team"])]]
    remaining = remaining[["home_team", "away_team"]].sort_values(["home_team", "away_team"])  # fixed order: same draws
    remaining = remaining.assign(match_id=remaining["home_team"] + "_" + remaining["away_team"]).reset_index(drop=True)

    season_teams = set(fixtures[["home_team", "away_team"]].stack())
    model = fit_latest(matches, season, params, cutoff, season_teams)
    forecasts = remaining.merge(pd.DataFrame(_predict_rows(model, remaining)), on="match_id")
    return simulate_season(played, forecasts, n_sims=n_sims, strength_sd=strength_sd)


def simulate_from_checkpoint(matches: pd.DataFrame, season: int, n_played: int, strength_sd: float,
                             n_sims: int, params: DCParams = DCParams()) -> pd.DataFrame:  # fmt: skip
    """Stop a past `season` after `n_played` matches and simulate the rest (used for tuning)."""
    this = matches[matches["season"] == season].sort_values(["date", "match_id"])
    cutoff = this["date"].iloc[n_played]  # everything from this date on is "the future"
    return simulate_as_of(matches, this, season, cutoff, n_sims, strength_sd, params)


def final_positions(matches: pd.DataFrame, season: int) -> dict[str, int]:
    """Actual final league positions (1 = champions), same tie-breaks as the simulation minus the coin toss."""
    from pipeline.export import league_table  # local import: export imports this module

    table = league_table(matches[matches["season"] == season])
    return dict(zip(table["team"], table["position"]))


def event_brier(sim: pd.DataFrame, positions: dict[str, int], n_teams: int = 20) -> float:
    """Mean Brier score of the title, top-4 and relegation chances against what happened."""
    errors = []
    for row in sim.itertuples():
        pos = positions[row.team]
        for prob, happened in ((row.p_title, pos == 1), (row.p_top4, pos <= 4), (row.p_relegation, pos > n_teams - 3)):
            errors.append((prob - happened) ** 2)
    return float(np.mean(errors))


def calibrate_strength_sd(matches: pd.DataFrame, seasons=TUNING_SEASONS,
                          grid=(0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3), n_sims: int = 2000) -> pd.DataFrame:  # fmt: skip
    """Score each strength_sd by Brier score over the tuning seasons and checkpoints (lower is better)."""
    rows = []
    for sd in grid:
        scores = [
            event_brier(simulate_from_checkpoint(matches, s, n, sd, n_sims), final_positions(matches, s))
            for s in seasons for n in CHECKPOINTS
        ]
        rows.append({"strength_sd": sd, "brier": float(np.mean(scores))})
        print(f"  strength_sd {sd:.2f}: Brier {rows[-1]['brier']:.5f}", flush=True)
    return pd.DataFrame(rows).sort_values("brier").reset_index(drop=True)


if __name__ == "__main__":
    from pipeline.data import PROCESSED_DIR

    data = pd.read_csv(PROCESSED_DIR / "matches.csv", parse_dates=["date"])
    print("Tuning the strength uncertainty on the tuning seasons...")
    print(calibrate_strength_sd(data).to_string(index=False))
