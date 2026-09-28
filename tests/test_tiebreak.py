"""Tests for Serie A's tie-break rules."""

import numpy as np

from pipeline.tiebreak import order_teams


def table(matches, n):
    """Points, goal difference, goals and match arrays from a list of (home, away, home_goals, away_goals)."""
    points, gd, gf = np.zeros(n), np.zeros(n), np.zeros(n)
    for h, a, hg, ag in matches:
        gf[h] += hg; gf[a] += ag; gd[h] += hg - ag; gd[a] += ag - hg  # fmt: skip
        points[h] += 3 if hg > ag else 1 if hg == ag else 0
        points[a] += 3 if ag > hg else 1 if hg == ag else 0
    arr = np.array(matches)
    return points, gd, gf, arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]


def test_head_to_head_beats_goal_difference():
    # 0 and 1 both end on 3 points; 1 has the better goal difference (+4 vs 0), but 0 beat 1
    matches = [(0, 1, 1, 0), (1, 2, 5, 0), (3, 0, 1, 0), (2, 3, 0, 0)]
    points, goal_diff = table(matches, 4)[:2]
    order = list(order_teams(*table(matches, 4)))
    assert points[0] == points[1] == 3 and goal_diff[1] > goal_diff[0]
    assert order.index(0) < order.index(1)


def test_goal_difference_decides_when_head_to_head_is_level():
    matches = [(0, 1, 1, 1), (0, 2, 3, 0), (1, 2, 1, 0)]  # 0 and 1 drew; both beat 2
    assert list(order_teams(*table(matches, 3))) == [0, 1, 2]


def test_three_way_tie_uses_the_mini_league():
    # 0, 1, 2 all on 3 points from beating each other in a circle; mini-league goal difference decides
    matches = [(0, 1, 3, 0), (1, 2, 1, 0), (2, 0, 1, 0)]
    assert order_teams(*table(matches, 3))[0] == 0  # +3 and -1: +2 in the mini-league


def test_title_playoff_is_a_coin_toss():
    matches = [(0, 1, 2, 0), (1, 0, 2, 0)]  # identical records: a two-way tie for first
    winners = [order_teams(*table(matches, 2), rng=np.random.default_rng(s), playoffs=True)[0] for s in range(400)]
    assert 0.4 < np.mean(np.array(winners) == 0) < 0.6
