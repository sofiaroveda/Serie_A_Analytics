// Table page: the standings now (data/table.json) and the predicted final table
// from 10,000 simulated seasons (data/simulation.json), switched with two tabs.
import { loadData, el, formatDate, showError } from "./common.js";
import { kitBadge } from "./teams.js";

/** Zone for a league position (Serie A: top 4 Champions League, 5-6 Europe, bottom 3 relegated). */
function zone(position, teams) {
  if (position <= 4) return "zone-cl";
  if (position <= 6) return "zone-europe";
  if (position > teams - 3) return "zone-releg";
  return "";
}

/** "34%", "<1%" for tiny chances, ">99%" for near-certain ones, "–" for never in 10,000 seasons. */
function chance(p) {
  if (p === 0) return "–";
  if (p < 0.005) return "<1%";
  if (p > 0.995) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** A table cell shaded by probability: `kind` is "good" (title, top 4, Europe) or "bad" (relegation). */
function chanceCell(p, kind, extraClass = "") {
  const cell = el("td", `chance ${kind} ${extraClass}`, chance(p));
  cell.style.setProperty("--strength", `${Math.round(p * 100)}%`);
  if (p > 0.55) cell.classList.add("strong"); // dark shade: switch text colour for contrast
  return cell;
}

function teamCell(team) {
  const cell = el("td", "team");
  cell.append(kitBadge(team), team);
  return cell;
}

function renderNow(table) {
  const body = document.getElementById("table-body");
  for (const team of table) {
    const goalDiff = team.goal_diff > 0 ? `+${team.goal_diff}` : String(team.goal_diff);
    const row = el("tr", zone(team.position, table.length));
    row.append(
      el("td", "pos", team.position), teamCell(team.team),
      el("td", "", team.played), el("td", "", team.won), el("td", "", team.drawn), el("td", "", team.lost),
      el("td", "hide-narrow", team.goals_for), el("td", "hide-narrow", team.goals_against),
      el("td", "", goalDiff), el("td", "pts", team.points),
    );
    body.append(row);
  }
}

function renderPredicted(sim) {
  document.getElementById("sim-intro").textContent =
    `We played out the remaining ${sim.remaining_matches} matches ${sim.n_sims.toLocaleString("en-GB")} times, ` +
    "drawing each score from our prediction for that match. These are the shares of simulated seasons in which " +
    "each team won the league, made the top 4, qualified for Europe or went down.";
  const body = document.getElementById("sim-body");
  sim.teams.forEach((team, i) => {
    const row = el("tr", zone(i + 1, sim.teams.length));
    row.append(
      el("td", "pos", i + 1), teamCell(team.team),
      el("td", "hide-narrow muted", team.points), el("td", "pts", Math.round(team.exp_points)),
      chanceCell(team.p_title, "good"), chanceCell(team.p_top4, "good"),
      chanceCell(team.p_europe, "good", "hide-narrow"), chanceCell(team.p_relegation, "bad"),
    );
    body.append(row);
  });
  document.getElementById("sim-note").textContent =
    "Ordered by expected final points. \"Pts\" is the average final total across all simulated seasons. Each " +
    "simulated season, every team is randomly a little stronger or weaker than its current rating, because form, " +
    "injuries and transfers change teams (how much was tuned on past seasons). Ties are broken by goal difference, " +
    "then goals scored.";
}

/** The Now / Predicted tabs. The choice is kept in the page address (#predicted) so it can be shared. */
function setUpTabs() {
  const tabs = { now: document.getElementById("tab-now"), predicted: document.getElementById("tab-predicted") };
  const show = (name) => {
    for (const [key, tab] of Object.entries(tabs)) {
      tab.setAttribute("aria-selected", String(key === name));
      document.getElementById(`view-${key}`).hidden = key !== name;
    }
    history.replaceState(null, "", name === "predicted" ? "#predicted" : location.pathname + location.search);
  };
  tabs.now.addEventListener("click", () => show("now"));
  tabs.predicted.addEventListener("click", () => show("predicted"));
  show(location.hash === "#predicted" ? "predicted" : "now");
}

async function main() {
  try {
    const [summary, table, sim] = await Promise.all([loadData("summary"), loadData("table"), loadData("simulation")]);
    document.getElementById("season").textContent = summary.season;
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    renderNow(table);
    renderPredicted(sim);
    setUpTabs();
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

main();
