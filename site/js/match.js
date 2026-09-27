// Small helpers about matches, shared by the Matches and Data lab pages.
import { el } from "./common.js";
import { kitBadge } from "./teams.js";

export const RESULT_TO_OUTCOME = { H: "home", D: "draw", A: "away" };
export const OUTCOMES = ["home", "draw", "away"];

/** Which outcome a forecast rated most likely: "home" | "draw" | "away". */
export function favourite(p) {
  return OUTCOMES.reduce((a, b) => (p[a] >= p[b] ? a : b));
}

/** Group matches by date, keeping their order: [["2026-09-20", [...]], ...] */
export function groupByDate(matches) {
  const groups = new Map();
  for (const match of matches) {
    if (!groups.has(match.date)) groups.set(match.date, []);
    groups.get(match.date).push(match);
  }
  return [...groups.entries()];
}

/** "Matchday 5 · full time", "Matchday 6 · coming up" or "Matchday 6 · 4 of 10 played". */
export function matchdayStatus(n, matches) {
  const played = matches.filter((m) => m.status === "played").length;
  if (played === matches.length) return `Matchday ${n} · full time`;
  if (played === 0) return `Matchday ${n} · coming up`;
  return `Matchday ${n} · ${played} of ${matches.length} played`;
}

function teamName(team, side) {
  const name = el("span", `team-name ${side}`);
  const label = el("span", "label", team);
  label.title = team; // full name on hover if it has to be shortened
  if (side === "home") name.append(kitBadge(team), label);
  else name.append(label, kitBadge(team));
  return name;
}

/** The top row of a match card: home team, score (or kick-off time), away team. */
export function matchHeader(match) {
  const teams = el("div", "match-teams");
  const middle = match.status === "played"
    ? el("span", "score", `${match.home_goals}–${match.away_goals}`)
    : el("span", "kickoff", match.time ?? "TBC");
  teams.append(teamName(match.home_team, "home"), middle, teamName(match.away_team, "away"));
  return teams;
}
