// How it works page: fills in the hit rates and the ratings table from the same data
// files the rest of the site uses, so the numbers are always current.
import { loadData, formatDate, percent, el, enableTooltips, showError } from "./common.js";
import { kitBadge } from "./teams.js";


async function main() {
  enableTooltips();
  try {
    const [summary, backtest, ratings] = await Promise.all([loadData("summary"), loadData("backtest"), loadData("ratings")]);
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    renderHitRates(backtest, summary);
    renderRatingsTable(ratings, summary.last_result_date);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

// ---------- How often are we right? ----------

function renderHitRates(backtest, summary) {
  const hit = backtest.overall.hit_rate;
  const rows = [
    ["Bookmakers (Pinnacle)", hit.pinnacle, ""],
    ["Our prediction", hit.dc, "ours"],
    ["Elo", hit.elo, ""],
    ["Always pick the home team", hit.base_rates, "baseline"],
    ["Pure guessing", 1 / 3, "baseline"],
  ];
  const container = document.getElementById("hit-rates");
  for (const [label, value, kind] of rows) {
    const row = el("div", `meter ${kind}`);
    const track = el("div", "meter-track");
    const fill = el("div", "meter-fill");
    fill.style.width = `${value * 100}%`;
    track.append(fill);
    row.append(el("span", "meter-label", label), track, el("span", "meter-value", `${(value * 100).toFixed(1)}%`));
    container.append(row);
  }
  const board = summary.scoreboard;
  document.getElementById("hit-rate-season").textContent =
    `Based on ${backtest.overall.matches.toLocaleString("en-GB")} matches from ${backtest.overall.season}.` +
    (board ? ` This season so far: ${percent(board.dc_hit_rate)} for our prediction and ${percent(board.market_hit_rate)} for the bookmakers, over ${board.matches} matches.` : "");
}

// ---------- Ratings table ----------

function renderRatingsTable(ratings, lastResult) {
  document.getElementById("ratings-note").textContent =
    `Ranked by Elo, using every result up to ${formatDate(lastResult)}. Attack above 1 = scores more than an ` +
    "average team; defence below 1 = concedes less (lower is better).";
  const body = document.getElementById("ratings-body");
  ratings.teams.forEach((team, i) => {
    const row = el("tr");
    const name = el("td", "team");
    name.append(kitBadge(team.team), team.team);
    row.append(
      el("td", "pos", i + 1), name, el("td", "pts", team.elo),
      el("td", team.attack >= 1 ? "good-num" : "", team.attack.toFixed(2)),
      el("td", team.defence <= 1 ? "good-num" : "", team.defence.toFixed(2)),
    );
    body.append(row);
  });
}

main();
