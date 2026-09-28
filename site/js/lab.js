// Data lab: our two models side by side with the bookmakers, this season's scoreboard,
// and the 12-season walk-forward backtest.
import { loadData, formatDate, percent, el, probs, probabilityBar, outcomeLegend, enableTooltips, showError } from "./common.js";
import { RESULT_TO_OUTCOME, OUTCOMES, groupByDate, matchHeader, matchdayStatus, matchUrl } from "./match.js";
import { setUpStrip } from "./strip.js";

// Forecasters shown for each match: key prefix in the data files and label
const FORECASTERS = [
  { prefix: "p", key: "market", label: "Bookmakers" },
  { prefix: "dc", key: "dc", label: "Goals model" },
  { prefix: "elo", key: "elo", label: "Elo" },
];
const GAP_WORTH_MENTIONING = 0.05; // 5 percentage points

let allMatches = [];

async function main() {
  enableTooltips();
  try {
    const [summary, matches, backtest] = await Promise.all([
      loadData("summary"), loadData("matches"), loadData("backtest"),
    ]);
    allMatches = matches;
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    setUpStrip({ matches, total: summary.matchdays, next: summary.current_matchday, onShow: renderMatchday });
    renderScoreboard(summary);
    renderBacktest(backtest);
    renderHitRates(backtest);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

// ---------- Match by match ----------

function renderMatchday(n) {
  const container = document.getElementById("matchday");
  const matches = allMatches.filter((m) => m.matchday === n);
  container.replaceChildren(el("h2", "", matchdayStatus(n, matches)), outcomeLegend());
  for (const [date, dayMatches] of groupByDate(matches)) {
    container.append(el("h3", "day-heading", formatDate(date)));
    for (const match of dayMatches) container.append(comparisonCard(match));
  }
}

function comparisonCard(match) {
  const happened = match.status === "played" ? RESULT_TO_OUTCOME[match.result] : null;
  const card = el("article", "match");
  card.append(matchHeader(match));

  const rows = el("div", "forecasts");
  for (const { prefix, label } of FORECASTERS) {
    const p = probs(match, prefix);
    rows.append(el("span", "forecast-label", label));
    rows.append(p ? probabilityBar(p, match, label, happened) : el("span", "muted small", "Odds not published yet"));
  }
  card.append(rows);

  const gap = disagreement(match);
  if (gap) card.append(gap);

  const facts = el("div", "facts");
  const addFact = (label, value) => {
    const item = el("span", "", `${label} `);
    item.append(el("strong", "", value));
    facts.append(item);
  };
  if (match.dc_xg_home !== null) addFact("Expected goals", `${match.dc_xg_home.toFixed(1)}–${match.dc_xg_away.toFixed(1)}`);
  if (match.dc_score) addFact("Most likely score", match.dc_score.replace("-", "–"));
  if (match.dc_over_2_5 !== null) addFact("Over 2.5 goals", percent(match.dc_over_2_5));
  if (match.dc_btts !== null) addFact("Both teams score", percent(match.dc_btts));
  if (match.odds_source) addFact("Odds", match.odds_source);
  card.append(facts);
  const more = el("a", "match-more", "Match page →");
  more.href = matchUrl(match);
  card.append(more);
  return card;
}

/** Where the goals model and the bookmakers differ most on this match (null if no odds yet). */
function disagreement(match) {
  const model = probs(match, "dc");
  const market = probs(match, "p");
  if (!model || !market) return null;
  const biggest = OUTCOMES.reduce((a, b) => (Math.abs(model[a] - market[a]) >= Math.abs(model[b] - market[b]) ? a : b));
  const gap = model[biggest] - market[biggest];
  if (Math.abs(gap) < GAP_WORTH_MENTIONING) {
    return el("p", "gap-note", "Model and bookmakers broadly agree (within 5 points on every outcome).");
  }
  const outcome = biggest === "draw" ? "a draw" : `${biggest === "home" ? match.home_team : match.away_team} winning`;
  const note = el("p", "gap-note strong");
  const points = Math.abs(Math.round(model[biggest] * 100) - Math.round(market[biggest] * 100)); // match the % shown
  note.append(el("strong", "", `${points}-point gap: `),
    `our model rates ${outcome} ${gap > 0 ? "higher" : "lower"} than the bookmakers (${percent(model[biggest])} vs ${percent(market[biggest])}).`);
  return note;
}

// ---------- This season's scoreboard ----------

function renderScoreboard(summary) {
  const board = summary.scoreboard;
  const container = document.getElementById("scoreboard");
  if (!board) {
    container.append(el("p", "empty", "No matches played yet this season."));
    return;
  }
  const rows = FORECASTERS.map(({ key, label }) => [label, board[`${key}_rps`], board[`${key}_hit_rate`]])
    .filter(([, value]) => value !== undefined)
    .sort((a, b) => a[1] - b[1]);
  const list = el("ol", "leaderboard");
  for (const [label, value, hits] of rows) {
    const item = el("li");
    item.append(el("span", "", label), el("span", "num muted small", `${percent(hits)} right`), el("span", "num", `RPS ${value.toFixed(4)}`));
    list.append(item);
  }
  container.append(list, el("p", "muted small",
    `Over ${board.matches} matches, ranked by Ranked Probability Score (lower is better). This early in the season the order is mostly luck.`));
}

// ---------- 12 seasons of testing ----------

function renderHitRates(backtest) {
  const labels = { ...backtest.forecasters, base_rates: "Always home" };
  const keys = Object.keys(labels);
  const head = document.getElementById("hits-head");
  head.append(el("th", "team", "Season"));
  for (const key of keys) head.append(el("th", "", labels[key]));
  const body = document.getElementById("hits-body");
  for (const row of [...backtest.seasons, backtest.overall]) {
    const isTotal = row === backtest.overall;
    const highest = Math.max(...keys.map((k) => row.hit_rate[k]));
    const tr = el("tr", isTotal ? "total" : "");
    tr.append(el("td", "team", isTotal ? "All seasons" : row.season));
    for (const key of keys) tr.append(el("td", row.hit_rate[key] === highest ? "pts" : "", `${(row.hit_rate[key] * 100).toFixed(1)}%`));
    body.append(tr);
  }
}

function renderBacktest(backtest) {
  const { overall, forecasters } = backtest;
  const keys = Object.keys(forecasters);
  const models = keys.filter((k) => k !== "base_rates" && k !== "pinnacle");
  const best = models.reduce((a, b) => (overall[a] <= overall[b] ? a : b));
  // Share of the bookmakers' improvement over guessing that our best model achieves
  const share = (overall.base_rates - overall[best]) / (overall.base_rates - overall.pinnacle);

  const stats = document.getElementById("backtest-stats");
  for (const [value, label] of [
    [overall[best].toFixed(4), `${forecasters[best]}, our best, ${overall.season}`],
    [overall.pinnacle.toFixed(4), "Pinnacle closing odds"],
    [percent(share), `of the bookmakers' edge over guessing that our ${forecasters[best].toLowerCase()} captures`],
  ]) {
    const box = el("div", "stat");
    box.append(el("div", "stat-value", value), el("div", "stat-label", label));
    stats.append(box);
  }

  const head = document.getElementById("backtest-head");
  head.append(el("th", "team", "Season"), el("th", "hide-narrow", "Matches"));
  for (const key of keys) head.append(el("th", "", forecasters[key]));

  const body = document.getElementById("backtest-body");
  for (const row of [...backtest.seasons, overall]) {
    const isTotal = row === overall;
    const lowest = Math.min(...keys.map((k) => row[k]));
    const tr = el("tr", isTotal ? "total" : "");
    tr.append(el("td", "team", isTotal ? "All seasons" : row.season));
    tr.append(el("td", "hide-narrow", row.matches.toLocaleString("en-GB")));
    for (const key of keys) tr.append(el("td", row[key] === lowest ? "pts" : "", row[key].toFixed(4))); // bold = most accurate
    body.append(tr);
  }
}

main();
