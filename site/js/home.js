// Matches page: talking points, then one matchday at a time with our prediction for each match.
import { loadData, formatDate, percent, el, probs, probabilityBar, outcomeLegend, enableTooltips, showError } from "./common.js";
import { RESULT_TO_OUTCOME, chanceText, groupByDate, matchHeader, matchdayStatus, matchUrl, verdict } from "./match.js";
import { setUpStrip } from "./strip.js";

// Our prediction comes from the goals model (Dixon-Coles), our most accurate model.
// The bookmakers and Elo are on the Data lab page.
const MAIN = "dc";

let allMatches = [];

async function main() {
  enableTooltips();
  try {
    // Load both files at the same time rather than one after another
    const [summary, matches, simulation] = await Promise.all([
      loadData("summary"), loadData("matches"), loadData("simulation"),
    ]);
    allMatches = matches;
    document.getElementById("season").textContent = summary.season;
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    renderTalkingPoints(matches, simulation);
    setUpStrip({ matches, total: summary.matchdays, next: summary.current_matchday, onShow: renderMatchday });
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

// ---------- Small helpers about one match ----------

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

function renderTalkingPoints(matches, simulation) {
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

  // From the season simulation: who is likely to win it, and who is in trouble
  if (simulation.remaining_matches > 0) {
    const favourites = [...simulation.teams].sort((a, b) => b.p_title - a.p_title);
    const [first, second] = favourites;
    points.unshift(["🏆", "Title race", `${first.team} ${percent(first.p_title)}`,
      `Chance of winning the league, ahead of ${second.team} (${percent(second.p_title)}). From 10,000 simulated seasons.`]);
    const danger = [...simulation.teams].sort((a, b) => b.p_relegation - a.p_relegation).slice(0, 3);
    points.splice(1, 0, ["⬇️", "Relegation battle", danger.map((t) => t.team).join(", "),
      `Most likely to go down: ${danger.map((t) => percent(t.p_relegation)).join(", ")} chance.`]);
  }

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

// ---------- One matchday ----------

function renderMatchday(n) {
  const container = document.getElementById("matchday");
  const matches = allMatches.filter((m) => m.matchday === n);
  container.replaceChildren(el("h2", "", matchdayStatus(n, matches)), outcomeLegend());
  for (const [date, dayMatches] of groupByDate(matches)) {
    container.append(el("h3", "day-heading", formatDate(date)));
    for (const match of dayMatches) container.append(matchCard(match));
  }
}

function matchCard(match) {
  const happened = match.status === "played" ? RESULT_TO_OUTCOME[match.result] : null;
  const card = el("article", "match");
  card.append(matchHeader(match));

  const p = probs(match, MAIN);
  if (!p) {
    card.append(el("p", "muted small", "Prediction not available."));
    return card;
  }
  card.append(el("div", "forecast-title", "Our prediction"), probabilityBar(p, match, "Our prediction", happened, { big: true }));
  card.append(verdict(match, p, happened));
  card.append(el("span", "match-more", match.status === "played" ? "Report and stats →" : "Match preview →"));
  // The whole card links to the match page
  const link = el("a", "match-link");
  link.href = matchUrl(match);
  link.append(card);
  return link;
}


main();
