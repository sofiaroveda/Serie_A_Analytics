// Model vs market page: walk-forward backtest from data/backtest.json.
import { loadData, el, percent, showError } from "./common.js";

async function main() {
  try {
    const backtest = await loadData("backtest");
    renderStats(backtest);
    renderTable(backtest);
    renderSettings(backtest.params);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

/** Our models: every forecaster except the two benchmarks. */
function modelKeys(backtest) {
  return Object.keys(backtest.forecasters).filter((k) => k !== "base_rates" && k !== "pinnacle");
}

function renderStats(backtest) {
  const { overall, forecasters } = backtest;
  const best = modelKeys(backtest).reduce((a, b) => (overall[a] <= overall[b] ? a : b));
  // Share of the market's improvement over base rates that our best model achieves
  const share = (overall.base_rates - overall[best]) / (overall.base_rates - overall.pinnacle);
  const stats = [
    [overall[best].toFixed(4), `${forecasters[best]} (our best model), ${overall.season}`],
    [overall.pinnacle.toFixed(4), "Pinnacle closing odds"],
    [percent(share), `of the market's edge over base rates that ${forecasters[best]} captures`],
  ];
  const container = document.getElementById("stats");
  for (const [value, label] of stats) {
    const box = el("div", "stat");
    box.append(el("div", "stat-value", value), el("div", "stat-label", label));
    container.append(box);
  }
}

function renderTable(backtest) {
  const keys = Object.keys(backtest.forecasters);

  const head = document.getElementById("backtest-head");
  head.append(el("th", "team", "Season"), el("th", "hide-narrow", "Matches"));
  for (const key of keys) head.append(el("th", "", backtest.forecasters[key]));

  const body = document.getElementById("backtest-body");
  for (const row of [...backtest.seasons, backtest.overall]) {
    const isTotal = row === backtest.overall;
    const best = Math.min(...keys.map((k) => row[k]));
    const tr = el("tr", isTotal ? "total" : "");
    tr.append(el("td", "team", isTotal ? "All seasons" : row.season));
    tr.append(el("td", "hide-narrow", row.matches.toLocaleString("en-GB")));
    for (const key of keys) tr.append(el("td", row[key] === best ? "pts" : "", row[key].toFixed(4))); // bold = most accurate
    body.append(tr);
  }
}

function renderSettings(params) {
  const e = params.elo;
  document.getElementById("settings-elo").textContent =
    `Elo settings: K = ${e.k}, home advantage = ${e.home_advantage}, pull back to average between seasons = ` +
    `${percent(e.season_regression)}, promoted teams start ${e.promoted_gap} points below average.`;
  const d = params.dc;
  document.getElementById("settings-dc").textContent =
    `Dixon-Coles settings: a match's weight halves every ${d.half_life_days} days; promoted teams start ` +
    `with a weaker-than-average prior. Both models' settings were chosen on the 2008/09 to 2013/14 seasons, ` +
    `before the test period.`;
}

main();
