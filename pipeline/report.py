"""Short written match reports, generated only from facts in our data.

Each sentence comes from one fact: the result, what our model expected, the
scorers (when openfootball has them), shots and expected goals, red cards, and how
the title / relegation chances moved after the matchday. Nothing is invented and
nothing is copied from other sites.
"""

from __future__ import annotations

import math


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def _is_number(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def result_sentence(m: dict) -> str:
    home, away, hg, ag = m["home_team"], m["away_team"], m["home_goals"], m["away_goals"]
    if hg == ag:
        return f"{home} and {away} played out a goalless draw." if hg == 0 else f"{home} and {away} drew {hg}–{ag}."
    home_won = hg > ag
    winner, loser = (home, away) if home_won else (away, home)
    score = f"{max(hg, ag)}–{min(hg, ag)}"
    p_winner = m.get("dc_home") if home_won else m.get("dc_away")
    margin = abs(hg - ag)
    if _is_number(p_winner) and p_winner < 0.25:
        verb = "stunned"
    elif margin >= 3:
        verb = "thrashed"
    elif margin == 2:
        verb = "beat"
    else:
        verb = "edged past"
    where = "" if home_won else " away from home"
    return f"{winner} {verb} {loser} {score}{where}."


def expectation_sentence(m: dict) -> str | None:
    probs = {"H": m.get("dc_home"), "D": m.get("dc_draw"), "A": m.get("dc_away")}
    if not all(_is_number(p) for p in probs.values()):
        return None
    names = {"H": m["home_team"], "A": m["away_team"]}
    favourite = max(probs, key=probs.get)
    happened = m["result"]
    if happened == favourite:
        if favourite == "D":
            return f"Our model had a draw as the most likely result ({_pct(probs['D'])})."
        strength = "narrow favourites" if probs[favourite] < 0.45 else "favourites"
        return f"It went to form: our model made {names[favourite]} {strength} at {_pct(probs[favourite])}."
    if happened != "D" and probs[happened] < 0.25:
        return f"A real upset: our model gave {names[happened]} only a {_pct(probs[happened])} chance."
    if happened == "D":
        return f"{names[favourite]} were favourites ({_pct(probs[favourite])}) but couldn't find a winner."
    return f"Not what we expected: our model had {names[favourite]} as favourites ({_pct(probs[favourite])})."


def scorers_sentence(m: dict, scorers: dict | None) -> str | None:
    if not scorers:
        return None

    def describe(goals: list[dict]) -> str:
        by_player: dict[str, list[str]] = {}
        for g in goals:
            label = f"{g['minute']}'" + (" pen" if g["penalty"] else "") + (" og" if g["own_goal"] else "")
            by_player.setdefault(g["player"], []).append(label)
        return ", ".join(f"{player} ({', '.join(minutes)})" for player, minutes in by_player.items())

    parts = []
    if scorers["home"]:
        parts.append(f"{describe(scorers['home'])} for {m['home_team']}")
    if scorers["away"]:
        parts.append(f"{describe(scorers['away'])} for {m['away_team']}")
    return "Goals: " + "; ".join(parts) + "."


def chances_sentence(m: dict) -> str | None:
    """Shots, and expected goals when the result and the chances created tell different stories."""
    home, away = m["home_team"], m["away_team"]
    sentences = []
    if all(_is_number(m.get(k)) for k in ("home_shots", "away_shots", "home_on_target", "away_on_target")):
        hs, as_, hst, ast = (int(m[k]) for k in ("home_shots", "away_shots", "home_on_target", "away_on_target"))
        sentences.append(f"{home} had {hs} shot{'s' * (hs != 1)} ({hst} on target) to {away}'s {as_} ({ast}).")
    if _is_number(m.get("home_xg")) and _is_number(m.get("away_xg")):
        hx, ax = m["home_xg"], m["away_xg"]
        xg = f"expected goals: {home} {hx:.1f}, {away} {ax:.1f}"
        hg, ag = m["home_goals"], m["away_goals"]
        if hg != ag:
            winner_xg, loser_xg = (hx, ax) if hg > ag else (ax, hx)
            winner = home if hg > ag else away
            if winner_xg + 0.3 < loser_xg:
                sentences.append(f"{winner} won despite creating less ({xg}).")
            elif winner_xg >= loser_xg + 1.0:
                sentences.append(f"A deserved win on the chances created ({xg}).")
        elif abs(hx - ax) >= 0.8:
            sentences.append(f"{home if hx > ax else away} will feel they deserved more ({xg}).")
    return " ".join(sentences) or None


def discipline_sentence(m: dict) -> str | None:
    """ "Monza finished with ten men." (players left on the pitch = 11 minus red cards)"""
    words = {10: "ten", 9: "nine", 8: "eight"}
    parts = []
    for side in ("home", "away"):
        reds = m.get(f"{side}_red")
        if _is_number(reds) and int(reds) > 0:
            parts.append(f"{m[f'{side}_team']} finished with {words.get(11 - int(reds), 'fewer')} men")
    return (" and ".join(parts) + ".") if parts else None


def impact_sentences(m: dict, before: dict | None, after: dict | None) -> list[str]:
    """How the matchday moved each team's headline chance (title, top 4 or relegation, whichever matters)."""
    if not before or not after:
        return []
    moves = []  # (team, label, from, to)
    for team in (m["home_team"], m["away_team"]):
        b, a = before.get(team), after.get(team)
        if not b or not a:
            continue
        for key, label in (("p_title", "title"), ("p_relegation", "relegation"), ("p_top4", "top-4")):
            threshold = 0.05 if key == "p_title" else 0.1
            if max(b[key], a[key]) >= threshold:
                if round(a[key] * 100) != round(b[key] * 100):
                    moves.append((team, label, _pct(b[key]), _pct(a[key])))
                break
    if not moves:
        return []
    first = f"After the round, {moves[0][0]}'s {moves[0][1]} chance went from {moves[0][2]} to {moves[0][3]}"
    if len(moves) == 1:
        return [first + "."]
    team, label, b, a = moves[1]
    second = f"{team}'s from {b} to {a}" if label == moves[0][1] else f"{team}'s {label} chance from {b} to {a}"
    return [f"{first}, and {second}."]


def match_report(m: dict, scorers: dict | None = None, before: dict | None = None, after: dict | None = None) -> str:
    """A short paragraph about a played match."""
    parts = [
        result_sentence(m),
        expectation_sentence(m),
        scorers_sentence(m, scorers),
        chances_sentence(m),
        discipline_sentence(m),
        *impact_sentences(m, before, after),
    ]
    return " ".join(p for p in parts if p)
