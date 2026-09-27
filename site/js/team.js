// Team page (team.html?team=Inter): the team's "share price" over the season, its biggest
// moves, form, ratings, next matches and results.
import { loadData, el, formatDate, probs, probabilityBar, enableTooltips, showError } from "./common.js";
import { kitBadge } from "./teams.js";
import { METRICS, price, changeBadge, series, teamLink } from "./stocks.js";
import { priceChart } from "./chart.js";

const MAIN = "dc"; // our prediction = the goals model

/** From the team's point of view: "W", "D" or "L". */
function outcomeFor(team, m) {
  const scored = m.home_team === team ? m.home_goals : m.away_goals;
  const conceded = m.home_team === team ? m.away_goals : m.home_goals;
  return scored > conceded ? "W" : scored === conceded ? "D" : "L";
}

/** "beat Lecce 3–0", "drew 1–1 with Milan", "lost 0–2 to Roma"; away games: "won 2–0 at Genoa" etc. (own goals first). */
function resultText(team, m) {
  const home = m.home_team === team;
  const opponent = home ? m.away_team : m.home_team;
  const score = home ? `${m.home_goals}–${m.away_goals}` : `${m.away_goals}–${m.home_goals}`;
  const phrases = home
    ? { W: `beat ${opponent} ${score}`, D: `drew ${score} with ${opponent}`, L: `lost ${score} to ${opponent}` }
    : { W: `won ${score} at ${opponent}`, D: `drew ${score} at ${opponent}`, L: `lost ${score} at ${opponent}` };
  return phrases[outcomeFor(team, m)];
}

function renderHeader(team, table, sim) {
  const row = table.find((t) => t.team === team);
  const title = document.getElementById("team-name");
  title.replaceChildren(kitBadge(team), team);
  document.title = `${team} · Serie A Analytics`;
  document.getElementById("team-summary").textContent = row
    ? `${ordinal(row.position)} in Serie A · ${row.points} points from ${row.played} games · expected to finish on about ${Math.round(sim.exp_points)} points`
    : "";
}

function ordinal(n) {
  const suffix = n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th";
  return `${n}${suffix}`;
}

function renderTickers(team, market) {
  const container = document.getElementById("tickers");
  const n = market.checkpoints.length;
  const last = market.checkpoints[n - 1].teams[team];
  const prev = market.checkpoints[Math.max(0, n - 2)].teams[team] ?? last;
  for (const m of Object.values(METRICS)) {
    const box = el("div", "stat ticker");
    const value = el("div", "stat-value", price(last[m.key]));
    if (last[m.key] > 0 || prev[m.key] > 0) value.append(" ", changeBadge(last[m.key] - prev[m.key], m.goodIfUp));
    box.append(el("div", "stat-label", m.label), value);
    container.append(box);
  }
}

/** The price chart, its metric tabs, and the biggest moves for the chosen metric. */
function renderChart(team, market, matches) {
  const show = (metricName) => {
    const m = METRICS[metricName];
    document.querySelectorAll("#metric-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.metric === metricName)));
    const values = series(market, team, m.key);
    const points = market.checkpoints.map((c, i) => ({
      label: c.label === "Start" ? "Start" : c.label.replace("MD ", ""),
      value: values[i],
      tip: `${c.label === "Start" ? "Before the season" : `After ${c.label}`}: ${price(values[i])} ${m.long}`,
    }));
    const chart = document.getElementById("price-chart");
    const width = Math.max(300, chart.clientWidth - 16); // match the box it sits in
    chart.replaceChildren(priceChart(points, { colour: m.colour, width, height: width < 500 ? 200 : 240 }));
    document.getElementById("chart-note").textContent =
      `${m.label}: the ${m.long} after each matchday (x-axis: matchday), from ${market.n_sims.toLocaleString("en-GB")} simulated seasons.`;
    renderMoves(team, market, matches, m);
  };
  document.querySelectorAll("#metric-tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.metric)));
  const favourite = market.checkpoints.at(-1).teams[team];
  // Open on the metric that matters most for this team: title contenders, top-4 hopefuls, or relegation
  show(favourite.p_title >= 0.05 ? "title" : favourite.p_relegation >= 0.1 ? "relegation" : "top4");
}

function renderMoves(team, market, matches, m) {
  const list = document.getElementById("moves");
  list.replaceChildren();
  const moves = [];
  for (let i = 1; i < market.checkpoints.length; i++) {
    const [before, after] = [market.checkpoints[i - 1], market.checkpoints[i]];
    const delta = after.teams[team][m.key] - before.teams[team][m.key];
    if (Math.abs(delta) < 0.02) continue; // under 2 points: not worth a headline
    const games = matches.filter((x) => x.status === "played" && (x.home_team === team || x.away_team === team)
      && x.date > before.as_of && x.date <= after.as_of);
    moves.push({ label: after.label, delta, before: before.teams[team][m.key], after: after.teams[team][m.key], games });
  }
  moves.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  if (!moves.length) {
    list.append(el("li", "muted", `No big moves yet: the ${m.label.toLowerCase()} chance hasn't changed by more than 2 points after any matchday.`));
    return;
  }
  for (const move of moves.slice(0, 4)) {
    const item = el("li");
    item.append(changeBadge(move.delta, m.goodIfUp), el("strong", "", ` ${move.label}`),
      `: ${price(move.before)} → ${price(move.after)}`,
      move.games.length ? ` after they ${move.games.map((g) => resultText(team, g)).join(" and ")}` : " (other results)");
    list.append(item);
  }
}

function renderForm(team, matches) {
  const played = matches.filter((m) => m.status === "played" && (m.home_team === team || m.away_team === team))
    .sort((a, b) => a.date.localeCompare(b.date));
  const form = document.getElementById("form");
  for (const m of played.slice(-5)) {
    const chip = el("span", `form-chip ${outcomeFor(team, m)}`, outcomeFor(team, m));
    chip.dataset.tip = `${formatDate(m.date)}: ${resultText(team, m)}`;
    form.append(chip);
  }
  const results = document.getElementById("results");
  for (const m of [...played].reverse()) {
    const row = el("li");
    row.append(el("span", `form-chip small ${outcomeFor(team, m)}`, outcomeFor(team, m)),
      el("span", "muted", `MD ${m.matchday} · ${formatDate(m.date)}`), ` ${resultText(team, m)}`);
    results.append(row);
  }
  if (!played.length) results.append(el("li", "muted", "No matches played yet."));
}

function renderRatings(team, ratings) {
  const rank = (key, lowerIsBetter = false) => {
    const sorted = [...ratings.teams].sort((a, b) => (lowerIsBetter ? a[key] - b[key] : b[key] - a[key]));
    return sorted.findIndex((t) => t.team === team) + 1;
  };
  const me = ratings.teams.find((t) => t.team === team);
  const container = document.getElementById("ratings");
  for (const [label, value, place, hint] of [
    ["Elo rating", me.elo, rank("elo"), "one number for overall strength"],
    ["Attack", me.attack.toFixed(2), rank("attack"), "goals scored vs an average team"],
    ["Defence", me.defence.toFixed(2), rank("defence", true), "goals conceded vs average (lower is better)"],
  ]) {
    const box = el("div", "stat");
    box.append(el("div", "stat-value", value), el("div", "stat-label", `${label} · ${ordinal(place)} in Serie A`), el("div", "stat-label small", hint));
    container.append(box);
  }
}

function renderNext(team, matches) {
  const next = matches.filter((m) => m.status === "upcoming" && (m.home_team === team || m.away_team === team)).slice(0, 5);
  const container = document.getElementById("next");
  if (!next.length) container.append(el("p", "muted", "No matches left this season."));
  for (const m of next) {
    const card = el("article", "match compact");
    const head = el("div", "compact-head");
    const opponent = m.home_team === team ? m.away_team : m.home_team;
    head.append(el("span", "muted small", `MD ${m.matchday} · ${formatDate(m.date)} · ${m.home_team === team ? "home" : "away"}`));
    const vs = el("span", "compact-vs");
    vs.append(m.home_team === team ? "vs " : "at ", teamLink(opponent));
    head.append(vs);
    card.append(head);
    const p = probs(m, MAIN);
    if (p) card.append(probabilityBar(p, m, "Our prediction", null));
    container.append(card);
  }
}

function renderTeamList(teams) {
  const main = document.querySelector("main");
  main.replaceChildren(el("h2", "", "Choose a team"));
  const grid = el("div", "team-grid");
  for (const team of [...teams].sort()) grid.append(teamLink(team));
  main.append(grid);
}

async function main() {
  enableTooltips();
  try {
    const [summary, matches, market, sim, ratings, table] = await Promise.all([
      loadData("summary"), loadData("matches"), loadData("market"), loadData("simulation"), loadData("ratings"), loadData("table"),
    ]);
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    const team = new URLSearchParams(location.search).get("team");
    const teams = sim.teams.map((t) => t.team);
    if (!teams.includes(team)) {
      document.getElementById("team-name").textContent = "Teams";
      document.getElementById("team-summary").textContent = `Every club in Serie A ${summary.season}.`;
      renderTeamList(teams);
      return;
    }
    renderHeader(team, table, sim.teams.find((t) => t.team === team));
    renderTickers(team, market);
    renderChart(team, market, matches);
    renderForm(team, matches);
    renderRatings(team, ratings);
    renderNext(team, matches);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

main();
