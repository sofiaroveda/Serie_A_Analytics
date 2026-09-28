"""Serie A's rules for ordering teams that finish level on points.

1. Points in the matches between the tied teams ("head-to-head", a mini-league)
2. Goal difference in those matches
3. Overall goal difference
4. Overall goals scored
5. Drawing lots

Exception: a two-team tie for first place, or across the relegation line, is settled
by a one-off play-off match. We can't know who would win it, so the simulation treats
it as a coin toss.
"""

from __future__ import annotations

import numpy as np

RELEGATION_PLACES = 3


def order_teams(
    points: np.ndarray,
    goal_diff: np.ndarray,
    goals_for: np.ndarray,
    home: np.ndarray,
    away: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    rng: np.random.Generator | None = None,
    playoffs: bool = False,
) -> np.ndarray:
    """Team indices in league order, best first.

    `points`, `goal_diff`, `goals_for` have one entry per team. `home`, `away`,
    `home_goals`, `away_goals` list the season's matches (team indices and scores),
    used for head-to-head. Final ties are broken at random with `rng`, or by team
    index without one. With `playoffs=True`, two-team ties for first place or across
    the relegation line are settled by a coin toss (the play-off).
    """
    n = len(points)
    lots = rng.random(n) if rng is not None else -np.arange(n, dtype=float)
    order = np.lexsort((lots, goals_for, goal_diff, points))[::-1]
    safe_places = n - RELEGATION_PLACES  # places 1..safe_places stay up

    ranked, i = [], 0
    while i < n:
        j = i
        while j + 1 < n and points[order[j + 1]] == points[order[i]]:
            j += 1
        group = order[i : j + 1]
        if len(group) > 1:
            group = _head_to_head(group, goal_diff, goals_for, lots, home, away, home_goals, away_goals)
            crosses_line = i == 0 or (i < safe_places <= j)  # tie for the title or for survival
            if playoffs and len(group) == 2 and crosses_line and rng is not None:
                group = group if rng.random() < 0.5 else group[::-1]  # the play-off: a coin toss
        ranked.extend(group)
        i = j + 1
    return np.array(ranked)


def _head_to_head(group, goal_diff, goals_for, lots, home, away, home_goals, away_goals):
    """Order a group of teams level on points by their mini-league, then overall GD, goals, lots."""
    in_group = np.isin(home, group) & np.isin(away, group)
    h, a = home[in_group], away[in_group]
    hg, ag = home_goals[in_group], away_goals[in_group]
    n = len(goal_diff)
    h2h_points, h2h_gd = np.zeros(n), np.zeros(n)
    np.add.at(h2h_points, h, np.where(hg > ag, 3, np.where(hg == ag, 1, 0)))
    np.add.at(h2h_points, a, np.where(ag > hg, 3, np.where(hg == ag, 1, 0)))
    np.add.at(h2h_gd, h, hg - ag)
    np.add.at(h2h_gd, a, ag - hg)
    keys = np.lexsort((lots[group], goals_for[group], goal_diff[group], h2h_gd[group], h2h_points[group]))[::-1]
    return group[keys]
