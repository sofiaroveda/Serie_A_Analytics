// Table page: one row per team from data/table.json, with European and relegation zones.
import { loadData, el, formatDate, showError } from "./common.js";
import { kitBadge } from "./teams.js";

/** Zone for a league position (Serie A: top 4 Champions League, 5-6 Europe, bottom 3 relegated). */
function zone(position, teams) {
  if (position <= 4) return "zone-cl";
  if (position <= 6) return "zone-europe";
  if (position > teams - 3) return "zone-releg";
  return "";
}

async function main() {
  const body = document.getElementById("table-body");
  try {
    const [summary, table] = await Promise.all([loadData("summary"), loadData("table")]);
    document.getElementById("season").textContent = summary.season;
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;

    for (const team of table) {
      const goalDiff = team.goal_diff > 0 ? `+${team.goal_diff}` : String(team.goal_diff);
      const row = el("tr", zone(team.position, table.length));
      const name = el("td", "team");
      name.append(kitBadge(team.team), team.team);
      row.append(
        el("td", "pos", team.position),
        name,
        el("td", "", team.played),
        el("td", "", team.won),
        el("td", "", team.drawn),
        el("td", "", team.lost),
        el("td", "hide-narrow", team.goals_for),
        el("td", "hide-narrow", team.goals_against),
        el("td", "", goalDiff),
        el("td", "pts", team.points),
      );
      body.append(row);
    }
  } catch (error) {
    showError(document.querySelector(".table-wrap"), error);
  }
}

main();
