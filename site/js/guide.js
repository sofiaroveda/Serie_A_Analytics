// How it works page: fills in the hit rates, the worked examples and the ratings table
// from the same data files the rest of the site uses, so the numbers are always current.
import { loadData, formatDate, percent, el, probabilityBar, enableTooltips, showError } from "./common.js";
import { kitBadge } from "./teams.js";

const MAX_GOALS = 10;

async function main() {
  enableTooltips();
  try {
    const [summary, backtest, ratings, matches] = await Promise.all([
      loadData("summary"), loadData("backtest"), loadData("ratings"), loadData("matches"),
    ]);
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    renderHitRates(backtest, summary);
    const teams = Object.fromEntries(ratings.teams.map((t) => [t.team, t]));
    renderGoalsExample(pickExample(matches, summary.current_matchday), teams, ratings.goals_model);
    renderEloExample(ratings);
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

// ---------- The goals model, step by step ----------

/** The upcoming match in the next matchday with the clearest favourite (it makes the best example). */
function pickExample(matches, matchday) {
  const candidates = matches.filter((m) => m.status === "upcoming" && m.dc_home !== null);
  const next = candidates.filter((m) => m.matchday === matchday);
  const pool = next.length ? next : candidates;
  return pool.reduce((a, b) => (Math.abs(b.dc_home - b.dc_away) > Math.abs(a.dc_home - a.dc_away) ? b : a));
}

/** Chance of k goals when `mean` are expected (the Poisson distribution). */
function poisson(k, mean) {
  let p = Math.exp(-mean);
  for (let i = 1; i <= k; i++) p *= mean / i;
  return p;
}

/** Chance of every score from 0-0 to 10-10, with the low-score correction; rows = home goals. */
function scoreMatrix(lam, mu, rho) {
  const m = [];
  let total = 0;
  for (let i = 0; i <= MAX_GOALS; i++) {
    m.push([]);
    for (let j = 0; j <= MAX_GOALS; j++) {
      let p = poisson(i, lam) * poisson(j, mu);
      if (i === 0 && j === 0) p *= 1 - lam * mu * rho;
      if (i === 0 && j === 1) p *= 1 + lam * rho;
      if (i === 1 && j === 0) p *= 1 + mu * rho;
      if (i === 1 && j === 1) p *= 1 - rho;
      m[i].push(p);
      total += p;
    }
  }
  return m.map((row) => row.map((p) => p / total));
}

function teamLabel(name) {
  const span = el("span", "team-inline");
  span.append(kitBadge(name), name);
  return span;
}

/** One line of the worked example: "label  =  a × b × c  =  result". */
function calcLine(label, parts, result) {
  const line = el("div", "calc");
  line.append(el("span", "calc-label", label));
  const sum = el("span", "calc-parts");
  parts.forEach(([value, caption], i) => {
    if (i) sum.append(el("span", "calc-op", "×"));
    const part = el("span", "calc-part");
    part.append(el("strong", "", value), el("small", "", caption));
    sum.append(part);
  });
  sum.append(el("span", "calc-op", "="), el("strong", "calc-result", result));
  line.append(sum);
  return line;
}

function renderGoalsExample(match, teams, model) {
  const home = teams[match.home_team];
  const away = teams[match.away_team];
  const lam = model.base_goals * model.home_boost * home.attack * away.defence;
  const mu = model.base_goals * away.attack * home.defence;

  // Step 2: expected goals
  const goals = document.getElementById("example-goals");
  const title = el("p", "example-title");
  title.append("Example: ", teamLabel(match.home_team), " v ", teamLabel(match.away_team), ` (${formatDate(match.date)})`);
  goals.append(title);
  goals.append(calcLine(`${match.home_team} goals`, [
    [model.base_goals.toFixed(2), "average"], [model.home_boost.toFixed(2), "home bonus"],
    [home.attack.toFixed(2), `${match.home_team} attack`], [away.defence.toFixed(2), `${match.away_team} defence`],
  ], lam.toFixed(1)));
  goals.append(calcLine(`${match.away_team} goals`, [
    [model.base_goals.toFixed(2), "average"],
    [away.attack.toFixed(2), `${match.away_team} attack`], [home.defence.toFixed(2), `${match.home_team} defence`],
  ], mu.toFixed(1)));

  // Step 3: a grid of the most common scores (0-4 each side), shaded by how likely they are
  const matrix = scoreMatrix(lam, mu, model.rho);
  const scores = document.getElementById("example-scores");
  const grid = el("div", "score-grid");
  grid.append(el("span", "corner", `${match.home_team} ↓ · ${match.away_team} →`));
  for (let j = 0; j <= 4; j++) grid.append(el("span", "axis", j));
  const top = Math.max(...matrix.slice(0, 5).flatMap((row) => row.slice(0, 5)));
  for (let i = 0; i <= 4; i++) {
    grid.append(el("span", "axis", i));
    for (let j = 0; j <= 4; j++) {
      const p = matrix[i][j];
      const cell = el("span", `cell ${i > j ? "home" : i === j ? "draw" : "away"}`, p < 0.005 ? "<1%" : percent(p));
      cell.style.setProperty("--strength", `${Math.round((p / top) * 100)}%`);
      if (p / top > 0.55) cell.classList.add("strong"); // dark shade: switch text colour for contrast
      cell.dataset.tip = `${match.home_team} ${i}–${j} ${match.away_team}: ${(p * 100).toFixed(1)}%`;
      grid.append(cell);
    }
  }
  scores.append(grid, el("p", "muted small", "Darker = more likely. Scores beyond 4 goals are counted too, they are just not shown."));

  // Step 4: add them up
  let pHome = 0, pDraw = 0, pAway = 0;
  matrix.forEach((row, i) => row.forEach((p, j) => {
    if (i > j) pHome += p; else if (i === j) pDraw += p; else pAway += p;
  }));
  const result = document.getElementById("example-result");
  result.append(probabilityBar({ home: pHome, draw: pDraw, away: pAway }, match, "Our prediction", null, { big: true }));
  result.append(el("p", "muted small",
    `${match.home_team} win ${percent(pHome)} · draw ${percent(pDraw)} · ${match.away_team} win ${percent(pAway)}. ` +
    "These are the numbers you see for this match on the Matches page (give or take rounding)."));
}

// ---------- Elo, worked through ----------

function renderEloExample(ratings) {
  const k = ratings.elo_k;
  const strong = ratings.teams[0];
  const weak = ratings.teams[ratings.teams.length - 1];
  const gap = strong.elo - weak.elo;
  const expected = 1 / (1 + 10 ** (-gap / 400)); // Elo's formula for the stronger side's expected score

  const box = document.getElementById("example-elo");
  const title = el("p", "example-title");
  title.append("Example: ", teamLabel(strong.team), ` (${strong.elo}) v `, teamLabel(weak.team), ` (${weak.elo})`);
  box.append(title);
  box.append(el("p", "", `A gap of ${gap} points means Elo expects ${strong.team} to take about ${percent(expected)} of the points on offer ` +
    `(a win counts as 1, a draw as ½). Here is how many rating points would change hands after a draw or a one-goal win:`));

  const list = el("ul", "elo-outcomes");
  const outcomes = [
    [`${strong.team} win`, 1],
    ["Draw", 0.5],
    [`${weak.team} win`, 0],
  ];
  for (const [label, score] of outcomes) {
    const change = k * (score - expected); // points the stronger team gains (negative = loses)
    const item = el("li");
    const who = change >= 0 ? strong.team : weak.team;
    item.append(el("strong", "", label), `: ${who} gain ${Math.abs(change).toFixed(1)} points, taken from ${who === strong.team ? weak.team : strong.team}`);
    list.append(item);
  }
  box.append(list, el("p", "muted small", "A shock result moves the ratings much more than an expected one. That is how Elo learns."));
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
