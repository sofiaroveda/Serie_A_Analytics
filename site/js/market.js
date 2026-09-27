// Market page: every team's chances, tracked like share prices after each matchday.
import { loadData, el, formatDate, enableTooltips, showError } from "./common.js";
import { METRICS, price, changeBadge, series, teamLink } from "./stocks.js";
import { sparkline } from "./chart.js";

let market;

function renderMovers(metric) {
  const m = METRICS[metric];
  const container = document.getElementById("movers");
  container.replaceChildren();
  const n = market.checkpoints.length;
  if (n < 2) return;
  const [prev, last] = [market.checkpoints[n - 2], market.checkpoints[n - 1]];
  const deltas = Object.keys(last.teams).map((team) => [team, last.teams[team][m.key] - (prev.teams[team]?.[m.key] ?? 0)]);
  const up = deltas.reduce((a, b) => (b[1] > a[1] ? b : a));
  const down = deltas.reduce((a, b) => (b[1] < a[1] ? b : a));
  for (const [kicker, [team, delta]] of [["Biggest riser", up], ["Biggest faller", down]]) {
    if (Math.round(delta * 100) === 0) continue;
    const card = el("a", "point mover");
    card.href = `team.html?team=${encodeURIComponent(team)}`;
    const icon = el("span", "point-icon", delta > 0 ? "📈" : "📉");
    icon.setAttribute("aria-hidden", "true");
    const headline = el("div", "point-headline");
    headline.append(team, " ", changeBadge(delta, m.goodIfUp));
    card.append(icon, el("div", "point-kicker", `${kicker} · ${m.label}`), headline,
      el("div", "point-detail", `${price(prev.teams[team]?.[m.key] ?? 0)} → ${price(last.teams[team][m.key])} since ${prev.label === "Start" ? "the start of the season" : `after ${prev.label}`}`));
    container.append(card);
  }
}

function renderBoard(metric) {
  const m = METRICS[metric];
  const n = market.checkpoints.length;
  const last = market.checkpoints[n - 1];
  const prev = market.checkpoints[Math.max(0, n - 2)];
  const teams = Object.keys(last.teams).sort((a, b) => last.teams[b][m.key] - last.teams[a][m.key]);

  document.getElementById("price-head").textContent = m.label;
  const body = document.getElementById("board-body");
  body.replaceChildren();
  teams.forEach((team, i) => {
    const row = el("tr");
    const name = el("td", "team");
    name.append(teamLink(team));
    const trend = el("td", "trend");
    trend.append(sparkline(series(market, team, m.key), { colour: m.colour }));
    const change = el("td", "");
    change.append(changeBadge(last.teams[team][m.key] - (prev.teams[team]?.[m.key] ?? 0), m.goodIfUp));
    row.append(el("td", "pos", i + 1), name, el("td", "pts", price(last.teams[team][m.key])), change, trend);
    body.append(row);
  });
  document.getElementById("board-note").textContent =
    `${m.label}: the ${m.long}, from ${market.n_sims.toLocaleString("en-GB")} simulated seasons after each matchday. ` +
    `Change is in percentage points since ${prev.label === "Start" ? "the start of the season" : `after ${prev.label}`}. ` +
    `Latest results: ${formatDate(last.as_of)}.`;
}

function setUpMetricTabs(onChange) {
  const buttons = [...document.querySelectorAll("#metric-tabs button")];
  const show = (metric) => {
    buttons.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.metric === metric)));
    history.replaceState(null, "", metric === "title" ? location.pathname + location.search : `#${metric}`);
    onChange(metric);
  };
  buttons.forEach((b) => b.addEventListener("click", () => show(b.dataset.metric)));
  const fromUrl = location.hash.slice(1);
  show(METRICS[fromUrl] ? fromUrl : "title");
}

async function main() {
  enableTooltips();
  try {
    const summary = await loadData("summary");
    market = await loadData("market");
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    setUpMetricTabs((metric) => {
      renderMovers(metric);
      renderBoard(metric);
    });
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

main();
