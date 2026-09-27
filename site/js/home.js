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
    renderTalkingPoints(matches);
    setUpStrip(summary.current_matchday);
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

// ---------- Talking points: headlines worked out from the results ----------

/** Each team's results so far, oldest first: { team: { results: ["W", "D", ...], gf, ga } }. */
function teamRecords(played) {
  const records = {};
  const add = (team, gf, ga) => {
    records[team] ??= { team, results: [], gf: 0, ga: 0 };
    records[team].results.push(gf > ga ? "W" : gf === ga ? "D" : "L");
    records[team].gf += gf;
    records[team].ga += ga;
  };
  for (const m of [...played].sort((a, b) => a.date.localeCompare(b.date))) {
    add(m.home_team, m.home_goals, m.away_goals);
    add(m.away_team, m.away_goals, m.home_goals);
  }
  return Object.values(records);
}

/** How many of the most recent results in a row pass `test`. */
function currentRun(results, test) {
  let n = 0;
  for (let i = results.length - 1; i >= 0 && test(results[i]); i--) n++;
  return n;
}

/** "1 win", "3 wins". */
function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** The item with the highest score (ties go to the first). */
function best(items, score) {
  return items.reduce((a, b) => (score(b) > score(a) ? b : a));
}

function renderTalkingPoints(matches) {
  const played = matches.filter((m) => m.status === "played");
  const section = document.getElementById("talking-points");
  if (!played.length) return;

  const points = [];
  const records = teamRecords(played);
  const wins = (r) => r.results.filter((x) => x === "W").length;

  // Biggest shock: the result our prediction rated least likely
  const withPrediction = played.filter((m) => probs(m, MAIN));
  if (withPrediction.length) {
    const chanceOf = (m) => probs(m, MAIN)[RESULT_TO_OUTCOME[m.result]];
    const shock = best(withPrediction, (m) => -chanceOf(m));
    const text = chanceText(shock, RESULT_TO_OUTCOME[shock.result], chanceOf(shock));
    points.push(["⚡", "Biggest shock", `${shock.home_team} ${shock.home_goals}–${shock.away_goals} ${shock.away_team}`,
      text[0].toUpperCase() + text.slice(1)]);
  }

  // In form: longest current unbeaten run (then most wins in that run, then goal difference)
  const unbeaten = (r) => currentRun(r.results, (x) => x !== "L");
  const winsInRun = (r) => r.results.slice(-unbeaten(r)).filter((x) => x === "W").length;
  const hot = best(records, (r) => unbeaten(r) * 1000 + winsInRun(r) * 10 + (r.gf - r.ga) / 100);
  if (unbeaten(hot) >= 2) {
    const run = unbeaten(hot);
    const w = winsInRun(hot);
    const span = run === hot.results.length ? `all ${run} games so far` : `their last ${run}`;
    points.push(["🔥", "In form", hot.team, w === run
      ? `Won ${span}`
      : `Unbeaten in ${span} (${plural(w, "win")}, ${plural(run - w, "draw")})`]);
  }

  // Struggling: longest current run without a win
  const winless = (r) => currentRun(r.results, (x) => x !== "W");
  const cold = best(records, (r) => winless(r) * 1000 + currentRun(r.results, (x) => x === "L") * 10 - (r.gf - r.ga) / 100);
  if (winless(cold) >= 2) {
    const lossRun = currentRun(cold.results, (x) => x === "L");
    points.push(["🥶", "Struggling", cold.team, lossRun === winless(cold)
      ? `Lost their last ${lossRun} in a row`
      : `No win in their last ${winless(cold)}`]);
  }

  // Goals: the most prolific attack
  const scorers = best(records, (r) => r.gf * 100 - r.results.length);
  const joint = records.filter((r) => r.gf === scorers.gf).length > 1;
  points.push(["⚽", "Goal machine", scorers.team,
    `${scorers.gf} goals in ${scorers.results.length} games, ${joint ? "joint " : ""}most in Serie A`]);

  section.append(el("h2", "section-kicker", "The story so far"));
  const grid = el("div", "points");
  for (const [icon, kicker, headline, detail] of points) {
    const card = el("article", "point");
    const iconEl = el("span", "point-icon", icon);
    iconEl.setAttribute("aria-hidden", "true");
    card.append(iconEl, el("div", "point-kicker", kicker), el("div", "point-headline", headline), el("div", "point-detail", detail));
    grid.append(card);
  }
  section.append(grid);
}

// ---------- Matchday strip ----------

/** The matchday in the page address (e.g. #matchday-4), if there is a valid one. */
function matchdayFromUrl() {
  const found = location.hash.match(/^#matchday-(\d+)$/);
  const n = found ? Number(found[1]) : null;
  return n >= 1 && n <= totalMatchdays ? n : null;
}

/** "10–12 Oct", "30 Sept–2 Oct" or "10 Oct". */
function shortRange(first, last) {
  const date = (d) => new Date(`${d}T12:00:00`);
  const day = (d) => date(d).getDate();
  const month = (d) => date(d).toLocaleDateString("en-GB", { month: "short" });
  if (first === last) return `${day(first)} ${month(first)}`;
  if (month(first) === month(last)) return `${day(first)}–${day(last)} ${month(last)}`;
  return `${day(first)} ${month(first)}–${day(last)} ${month(last)}`;
}

/** The dates of a matchday, ignoring postponed games played weeks later. */
function matchdayDates(n) {
  const dates = allMatches.filter((m) => m.matchday === n).map((m) => m.date).sort();
  if (!dates.length) return "";
  const middle = new Date(dates[Math.floor(dates.length / 2)]);
  const near = dates.filter((d) => Math.abs(new Date(d) - middle) <= 4 * 86_400_000);
  return shortRange(near[0], near[near.length - 1]);
}

function setUpStrip(nextMatchday) {
  const scroller = document.getElementById("md-scroller");
  const chips = [];
  for (let n = 1; n <= totalMatchdays; n++) {
    const dates = matchdayDates(n);
    const chip = el("button", `md-chip${n === nextMatchday ? " is-next" : ""}`);
    chip.type = "button";
    chip.append(el("span", "md-num", `MD ${n}`), el("span", "md-dates", n === nextMatchday ? `Next · ${dates}` : dates));
    chip.setAttribute("aria-label", `Matchday ${n}, ${dates}${n === nextMatchday ? ", next to be played" : ""}`);
    chip.addEventListener("click", () => show(n));
    scroller.append(chip);
    chips.push(chip);
  }

  let current = nextMatchday;
  function show(n, smooth = true) {
    current = n;
    chips.forEach((chip, i) => chip.setAttribute("aria-pressed", String(i + 1 === n)));
    // Slide the strip so the chosen chip is in the middle (without scrolling the page)
    const chip = chips[n - 1];
    scroller.scrollTo({
      left: chip.offsetLeft - scroller.clientWidth / 2 + chip.offsetWidth / 2,
      behavior: smooth ? "smooth" : "auto",
    });
    document.getElementById("prev").disabled = n <= 1;
    document.getElementById("next").disabled = n >= totalMatchdays;
    history.replaceState(null, "", `#matchday-${n}`); // update the address without reloading
    renderMatchday(n);
  }

  document.getElementById("prev").addEventListener("click", () => show(current - 1));
  document.getElementById("next").addEventListener("click", () => show(current + 1));
  window.addEventListener("hashchange", () => matchdayFromUrl() && show(matchdayFromUrl()));
  show(matchdayFromUrl() ?? nextMatchday, false);
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
