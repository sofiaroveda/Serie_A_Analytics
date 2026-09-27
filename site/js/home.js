// Home page: headline stats and one matchday at a time, chosen from a dropdown.
import {
  loadData, formatDate, percent, el, probs, probabilityBar, outcomeLegend, enableTooltips, showError,
} from "./common.js";

// Each forecaster: its key prefix in the data files and the label shown on the page
const FORECASTERS = [
  { prefix: "p", label: "Market" },
  { prefix: "elo", label: "Elo model" },
];
const SURPRISE_THRESHOLD = 0.25; // flag results the market rated below 25%
const RESULT_TO_OUTCOME = { H: "home", D: "draw", A: "away" };

let allMatches = [];
let totalMatchdays = 38;

async function main() {
  enableTooltips();
  try {
    // Load both files at the same time rather than one after another
    const [summary, matches] = await Promise.all([loadData("summary"), loadData("matches")]);
    allMatches = matches;
    totalMatchdays = summary.matchdays;
    document.getElementById("season").textContent = summary.season;
    document.getElementById("updated").textContent = `Updated ${summary.generated_at.slice(0, 10)}.`;
    renderStats(summary);
    setUpPicker(summary.current_matchday);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

function renderStats(summary) {
  const stats = [
    [summary.matches_played, "matches played"],
    [summary.favourite_win_rate === null ? "–" : percent(summary.favourite_win_rate), "won by the market favourite"],
  ];
  const board = summary.scoreboard;
  if (board) {
    stats.push([
      `${board.elo_rps.toFixed(3)} vs ${board.market_rps.toFixed(3)}`,
      "Elo vs market accuracy this season (RPS, lower is better)",
    ]);
  }
  const container = document.getElementById("stats");
  for (const [value, label] of stats) {
    const box = el("div", "stat");
    box.append(el("div", "stat-value", value), el("div", "stat-label", label));
    container.append(box);
  }
}

// ---------- Matchday picker ----------

/** The matchday in the page address (e.g. #matchday-4), if there is a valid one. */
function matchdayFromUrl() {
  const found = location.hash.match(/^#matchday-(\d+)$/);
  const n = found ? Number(found[1]) : null;
  return n >= 1 && n <= totalMatchdays ? n : null;
}

function setUpPicker(defaultMatchday) {
  const select = document.getElementById("matchday-select");
  for (let n = 1; n <= totalMatchdays; n++) {
    const option = el("option", "", `Matchday ${n}`);
    option.value = n;
    if (n === defaultMatchday) option.textContent += " (next)";
    select.append(option);
  }

  const show = (n) => {
    select.value = n;
    document.getElementById("prev").disabled = n <= 1;
    document.getElementById("next").disabled = n >= totalMatchdays;
    history.replaceState(null, "", `#matchday-${n}`); // update the address without reloading
    renderMatchday(n);
  };

  select.addEventListener("change", () => show(Number(select.value)));
  document.getElementById("prev").addEventListener("click", () => show(Number(select.value) - 1));
  document.getElementById("next").addEventListener("click", () => show(Number(select.value) + 1));
  window.addEventListener("hashchange", () => matchdayFromUrl() && show(matchdayFromUrl()));

  show(matchdayFromUrl() ?? defaultMatchday);
}

function renderMatchday(n) {
  const container = document.getElementById("matchday");
  const matches = allMatches.filter((m) => m.matchday === n);
  container.replaceChildren();

  const played = matches.filter((m) => m.status === "played").length;
  const status =
    played === matches.length ? "All matches played." :
    played === 0 ? "Not played yet. Elo forecasts use the latest ratings; market odds appear a few days before kick-off." :
    `${played} of ${matches.length} matches played.`;
  container.append(el("p", "muted small", status));
  container.append(outcomeLegend());
  if (played > 0) container.append(el("p", "muted small", "For played matches, the outlined segment is what happened."));

  for (const [date, dayMatches] of groupByDate(matches)) {
    container.append(el("h3", "day-heading", formatDate(date)));
    for (const match of dayMatches) container.append(matchCard(match));
  }
}

/** Group matches by date, keeping their order: [["2026-09-20", [...]], ...] */
function groupByDate(matches) {
  const groups = new Map();
  for (const match of matches) {
    if (!groups.has(match.date)) groups.set(match.date, []);
    groups.get(match.date).push(match);
  }
  return [...groups.entries()];
}

// ---------- One match ----------

function matchCard(match) {
  const played = match.status === "played";
  const card = el("article", "match");

  const teams = el("div", "match-teams");
  const middle = played ? `${match.home_goals}–${match.away_goals}` : match.time ?? "vs";
  teams.append(el("span", "", match.home_team), el("span", "score", middle), el("span", "away-name", match.away_team));
  card.append(teams);

  const happened = played ? RESULT_TO_OUTCOME[match.result] : null;
  const rows = el("div", "forecasts");
  for (const { prefix, label } of FORECASTERS) {
    const p = probs(match, prefix);
    rows.append(el("span", "forecast-label", label));
    rows.append(p ? probabilityBar(p, match, label, happened) : el("span", "muted small", "Not available yet"));
  }
  card.append(rows);

  const meta = el("div", "match-meta");
  if (match.odds_source) meta.append(el("span", "", `Market odds: ${match.odds_source}`));
  if (happened && match.p_home !== null && match[`p_${happened}`] < SURPRISE_THRESHOLD) {
    meta.append(el("span", "tag", `⚡ Surprise: the market gave this ${percent(match[`p_${happened}`])}`));
  }
  if (meta.childElementCount) card.append(meta);
  return card;
}

main();
