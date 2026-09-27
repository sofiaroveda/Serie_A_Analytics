// Table page: one row per team from data/table.json.
import { loadData, el, showError } from "./common.js";

async function main() {
  const body = document.getElementById("table-body");
  try {
    const [summary, table] = await Promise.all([loadData("summary"), loadData("table")]);
    document.getElementById("season").textContent = summary.season;

    for (const team of table) {
      const goalDiff = team.goal_diff > 0 ? `+${team.goal_diff}` : String(team.goal_diff);
      const row = el("tr");
      row.append(
        el("td", "", team.position),
        el("td", "team", team.team),
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
