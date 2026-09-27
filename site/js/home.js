// Home page: headline stats, upcoming fixtures and latest results.
import {
  loadData, formatDate, percent, el, probabilityBar, outcomeLegend, enableTooltips, showError,
} from "./common.js";

const RESULTS_SHOWN_AT_FIRST = 20; // about two rounds
const SURPRISE_THRESHOLD = 0.25; // flag results the market rated below 25%
const RESULT_TO_OUTCOME = { H: "home", D: "draw", A: "away" };

async function main() {
  enableTooltips();
  try {
    // Load the three files at the same time rather than one after another
    const [summary, fixtures, results] = await Promise.all([
      loadData("summary"), loadData("fixtures"), loadData("results"),
    ]);
    document.getElementById("season").textContent = summary.season;
    document.getElementById("updated").textContent = `Updated ${summary.generated_at.slice(0, 10)}.`;
    renderStats(summary);
    renderFixtures(fixtures);
    renderResults(results);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

function renderStats(summary) {
  const stats = [
    [summary.matches_played, "matches played"],
    [summary.favourite_win_rate === null ? "–" : percent(summary.favourite_win_rate), "won by the market favourite"],
    [formatDate(summary.last_result_date), "latest result"],
  ];
  const container = document.getElementById("stats");
  for (const [value, label] of stats) {
    const box = el("div", "stat");
    box.append(el("div", "stat-value", value), el("div", "stat-label", label));
    container.append(box);
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

function matchCard(match, { played }) {
  const card = el("article", "match");

  const teams = el("div", "match-teams");
  const middle = played ? `${match.home_goals}–${match.away_goals}` : match.time ?? "vs";
  teams.append(el("span", "", match.home_team), el("span", "score", middle), el("span", "away-name", match.away_team));
  card.append(teams);

  if (match.p_home === null) {
    card.append(el("p", "muted small", "No odds available for this match."));
    return card;
  }

  const happened = played ? RESULT_TO_OUTCOME[match.result] : null;
  card.append(probabilityBar(match, happened));

  const meta = el("div", "match-meta");
  meta.append(el("span", "", match.odds_source));
  if (happened && match[`p_${happened}`] < SURPRISE_THRESHOLD) {
    meta.append(el("span", "tag", `⚡ Surprise: the market gave this ${percent(match[`p_${happened}`])}`));
  }
  card.append(meta);
  return card;
}

function renderMatchList(container, matches, options) {
  for (const [date, dayMatches] of groupByDate(matches)) {
    container.append(el("h3", "day-heading", formatDate(date)));
    for (const match of dayMatches) container.append(matchCard(match, options));
  }
}

function renderFixtures(fixtures) {
  const container = document.getElementById("fixtures");
  if (fixtures.length === 0) {
    container.append(el("p", "empty", "The odds for the next round aren't published yet. They usually appear a few days before the matches."));
    return;
  }
  container.append(outcomeLegend());
  renderMatchList(container, fixtures, { played: false });
}

function renderResults(results) {
  const container = document.getElementById("results");
  if (results.length === 0) {
    container.append(el("p", "empty", "No matches played yet this season."));
    return;
  }
  container.append(outcomeLegend());
  container.append(el("p", "muted small", "The outlined segment is what actually happened."));

  const list = el("div");
  container.append(list);
  renderMatchList(list, results.slice(0, RESULTS_SHOWN_AT_FIRST), { played: true });

  if (results.length > RESULTS_SHOWN_AT_FIRST) {
    const button = el("button", "more", `Show all ${results.length} results`);
    button.addEventListener("click", () => {
      list.replaceChildren();
      renderMatchList(list, results, { played: true });
      button.remove();
    });
    container.append(button);
  }
}

main();
