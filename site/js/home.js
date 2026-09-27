// Home page: a few headline numbers and one matchday at a time, chosen from a dropdown.
import {
  loadData, formatDate, percent, el, probs, probabilityBar, outcomeLegend, enableTooltips, showError,
} from "./common.js";
import { kitBadge } from "./teams.js";

// Our headline prediction comes from the goals model (Dixon-Coles), our most accurate model.
const MAIN = "dc";
// Shown in the "Compare with bookmakers" panel: key prefix in the data and label
const COMPARISON = [
  { prefix: "p", label: "Bookmakers" },
  { prefix: "dc", label: "Goals model" },
  { prefix: "elo", label: "Elo" },
];
const RESULT_TO_OUTCOME = { H: "home", D: "draw", A: "away" };
const OUTCOMES = ["home", "draw", "away"];

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
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    renderStats(matches, summary);
    setUpPicker(summary.current_matchday);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

// ---------- Small helpers about one match ----------

/** Which outcome a forecast rated most likely: "home" | "draw" | "away". */
function favourite(p) {
  return OUTCOMES.reduce((a, b) => (p[a] >= p[b] ? a : b));
}

/** "we gave Cagliari an 18% chance of winning" / "we gave a draw a 28% chance". */
function chanceText(match, outcome, p) {
  const pct = percent(p);
  const article = /^(8|11|18)/.test(pct) ? "an" : "a"; // "an 18%", "a 28%"
  if (outcome === "draw") return `we gave a draw ${article} ${pct} chance`;
  const team = outcome === "home" ? match.home_team : match.away_team;
  return `we gave ${team} ${article} ${pct} chance of winning`;
}

/** A short sentence about who is expected to win. */
function outlook(match, p) {
  const fav = favourite(p);
  if (fav === "draw") return "A draw is the single most likely result";
  const team = fav === "home" ? match.home_team : match.away_team;
  if (p[fav] >= 0.6) return `${team} strong favourites`;
  if (p[fav] >= 0.45) return `${team} favourites`;
  return `Close call, ${team} slightly ahead`;
}

// ---------- Headline numbers ----------

function renderStats(matches, summary) {
  const played = matches.filter((m) => m.status === "played" && m[`${MAIN}_home`] !== null);
  const container = document.getElementById("stats");
  const addStat = (value, label, { wide = false } = {}) => {
    const box = el("div", `stat${wide ? " wide" : ""}`);
    box.append(el("div", `stat-value${wide ? " compact" : ""}`, value), el("div", "stat-label", label));
    container.append(box);
  };

  if (played.length) {
    const called = played.filter((m) => favourite(probs(m, MAIN)) === RESULT_TO_OUTCOME[m.result]).length;
    addStat(`${called}/${played.length}`, "results we called right");

    // Biggest upset: the result we rated least likely
    const upset = played.reduce((a, b) =>
      probs(a, MAIN)[RESULT_TO_OUTCOME[a.result]] <= probs(b, MAIN)[RESULT_TO_OUTCOME[b.result]] ? a : b);
    const chance = probs(upset, MAIN)[RESULT_TO_OUTCOME[upset.result]];
    if (summary.favourite_win_rate !== null) {
      addStat(percent(summary.favourite_win_rate), "won by the bookmakers' favourite");
    }
    addStat(`${upset.home_team} ${upset.home_goals}–${upset.away_goals} ${upset.away_team}`,
      `Biggest shock so far: ${chanceText(upset, RESULT_TO_OUTCOME[upset.result], chance)}`, { wide: true });
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
    if (n === defaultMatchday) option.textContent += " · next";
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
    played === matches.length ? `Matchday ${n} · full time` :
    played === 0 ? `Matchday ${n} · coming up` :
    `Matchday ${n} · ${played} of ${matches.length} played`;
  container.append(el("h2", "", status));
  container.append(outcomeLegend());

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

function teamName(team, side) {
  const name = el("span", `team-name ${side}`);
  const label = el("span", "label", team);
  label.title = team; // full name on hover if it has to be shortened
  if (side === "home") name.append(kitBadge(team), label);
  else name.append(label, kitBadge(team));
  return name;
}

function matchCard(match) {
  const played = match.status === "played";
  const happened = played ? RESULT_TO_OUTCOME[match.result] : null;
  const card = el("article", "match");

  const teams = el("div", "match-teams");
  const middle = played
    ? el("span", "score", `${match.home_goals}–${match.away_goals}`)
    : el("span", "kickoff", match.time ?? "TBC");
  teams.append(teamName(match.home_team, "home"), middle, teamName(match.away_team, "away"));
  card.append(teams);

  const p = probs(match, MAIN);
  if (!p) {
    card.append(el("p", "muted small", "Prediction not available."));
    return card;
  }

  card.append(el("div", "forecast-title", "Our prediction"), probabilityBar(p, match, "Our prediction", happened, { big: true }));
  card.append(verdict(match, p, happened));
  card.append(details(match, happened));
  return card;
}

/** One line under the bar: the outlook before the match, or how the prediction did after it. */
function verdict(match, p, happened) {
  if (!happened) return el("div", "verdict neutral", outlook(match, p));
  const detail = el("span", "detail", `· ${chanceText(match, happened, p[happened])}`);
  if (favourite(p) === happened) {
    const line = el("div", "verdict good", "✓ Called it ");
    line.append(detail);
    return line;
  }
  const upset = happened !== "draw" && p[happened] < 0.25; // a team winning when we gave it under 25%
  const line = el("div", "verdict bad", upset ? "✗ Upset " : "✗ Not this time ");
  line.append(detail);
  return line;
}

/** The expandable "Compare with bookmakers" panel. */
function details(match, happened) {
  const panel = el("details", "more-info");
  panel.append(el("summary", "", "Compare with bookmakers"));

  const rows = el("div", "forecasts");
  for (const { prefix, label } of COMPARISON) {
    const p = probs(match, prefix);
    rows.append(el("span", "forecast-label", label));
    rows.append(p ? probabilityBar(p, match, label, happened) : el("span", "muted small", "Odds not published yet"));
  }
  panel.append(rows);

  const facts = el("div", "facts");
  const addFact = (label, value) => {
    const item = el("span", "", `${label} `);
    item.append(el("strong", "", value));
    facts.append(item);
  };
  if (match.dc_xg_home !== null) addFact("Expected goals", `${match.dc_xg_home.toFixed(1)}–${match.dc_xg_away.toFixed(1)}`);
  if (match.dc_score) addFact("Single most likely score", match.dc_score.replace("-", "–"));
  if (match.dc_over_2_5 !== null) addFact("Over 2.5 goals", percent(match.dc_over_2_5));
  if (match.dc_btts !== null) addFact("Both teams score", percent(match.dc_btts));
  if (match.odds_source) addFact("Odds", match.odds_source);
  panel.append(facts);
  return panel;
}

main();
