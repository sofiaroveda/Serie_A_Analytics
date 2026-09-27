// Model vs market page: walk-forward backtest from data/backtest.json.
import { loadData, el, percent, showError } from "./common.js";

const FORECASTERS = ["base_rates", "elo", "pinnacle"];

async function main() {
  try {
    const backtest = await loadData("backtest");
    renderStats(backtest.overall);
    renderTable(backtest);
    const s = backtest.elo_params;
    document.getElementById("settings").textContent =
      `Elo settings (chosen on the 2008/09 to 2013/14 seasons, before the test period): ` +
      `K = ${s.k}, home advantage = ${s.home_advantage}, pull back to average between seasons = ` +
      `${percent(s.season_regression)}, promoted teams start ${s.promoted_gap} points below average.`;
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

function renderStats(overall) {
  // Share of the market's improvement over base rates that Elo achieves
  const share = (overall.base_rates - overall.elo) / (overall.base_rates - overall.pinnacle);
  const stats = [
    [overall.elo.toFixed(4), `Elo RPS, ${overall.season}`],
    [overall.pinnacle.toFixed(4), "Pinnacle closing odds RPS"],
    [percent(share), "of the market's edge over base rates that Elo captures"],
  ];
  const container = document.getElementById("stats");
  for (const [value, label] of stats) {
    const box = el("div", "stat");
    box.append(el("div", "stat-value", value), el("div", "stat-label", label));
    container.append(box);
  }
}

function renderTable(backtest) {
  const body = document.getElementById("backtest-body");
  for (const row of [...backtest.seasons, backtest.overall]) {
    const best = Math.min(...FORECASTERS.map((f) => row[f]));
    const tr = el("tr");
    tr.append(el("td", "team", row === backtest.overall ? "All seasons" : row.season));
    tr.append(el("td", "hide-narrow", row.matches.toLocaleString("en-GB")));
    for (const f of FORECASTERS) {
      const cell = el("td", row[f] === best ? "pts" : "", row[f].toFixed(4)); // bold = most accurate
      tr.append(cell);
    }
    if (row === backtest.overall) tr.classList.add("total");
    body.append(tr);
  }
}

main();
