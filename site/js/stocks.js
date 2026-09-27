// Shared "stock market" helpers, used by the Market page and the team pages.
import { el } from "./common.js";
import { kitBadge } from "./teams.js";

// What can be "traded": each metric's key in market.json, label, colour, and whether a rise is good news
export const METRICS = {
  title: { key: "p_title", label: "Title", long: "chance of winning the league", colour: "var(--accent)", goodIfUp: true },
  top4: { key: "p_top4", label: "Top 4", long: "chance of a top-4 (Champions League) finish", colour: "var(--zone-cl)", goodIfUp: true },
  relegation: { key: "p_relegation", label: "Relegation", long: "chance of going down", colour: "var(--zone-releg)", goodIfUp: false },
};

/** "34%", "<1%", ">99%" or "–" (never happened in 10,000 simulated seasons). */
export function price(p) {
  if (p === 0) return "–";
  if (p < 0.005) return "<1%";
  if (p > 0.995) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** A change in percentage points as "▲ 4" / "▼ 3" / "–", coloured by whether it's good news for the team. */
export function changeBadge(delta, goodIfUp) {
  const points = Math.round(delta * 100);
  if (points === 0) return el("span", "change flat", "–");
  const good = (points > 0) === goodIfUp;
  const badge = el("span", `change ${good ? "up" : "down"}`, `${points > 0 ? "▲" : "▼"} ${Math.abs(points)}`);
  badge.title = `${points > 0 ? "Up" : "Down"} ${Math.abs(points)} percentage points since the previous matchday`;
  return badge;
}

/** One team's values of a metric at every checkpoint, oldest first. */
export function series(market, team, key) {
  return market.checkpoints.map((c) => c.teams[team]?.[key] ?? 0);
}

export function teamLink(team) {
  const link = el("a", "team-link");
  link.href = `team.html?team=${encodeURIComponent(team)}`;
  link.append(kitBadge(team), team);
  return link;
}
