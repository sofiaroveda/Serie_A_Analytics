// Match page (match.html?id=...): the report, scorers and stats after full time; our prediction,
// the most likely scores and the form guide before kick-off; past meetings either way.
import { loadData, el, formatDate, percent, probs, probabilityBar, enableTooltips, showError } from "./common.js";
import { RESULT_TO_OUTCOME, verdict } from "./match.js";
import { kitBadge } from "./teams.js";
import { teamLink } from "./stocks.js";

const MAIN = "dc"; // our prediction = the goals model

// Rows of the stats comparison: label and the key in match_details stats (home_/away_ prefix added)
const STAT_ROWS = [
  ["Expected goals (xG)", "xg", 1],
  ["Shots", "shots", 0],
  ["Shots on target", "on_target", 0],
  ["Corners", "corners", 0],
  ["Fouls", "fouls", 0],
  ["Yellow cards", "yellow", 0],
  ["Red cards", "red", 0],
];

function section(title, ...children) {
  const wrap = el("section", "match-section");
  wrap.append(el("h2", "", title), ...children);
  return wrap;
}

function renderHero(match) {
  const title = document.getElementById("match-title");
  const home = el("span", "hero-team");
  home.append(kitBadge(match.home_team), match.home_team);
  const away = el("span", "hero-team");
  away.append(match.away_team, kitBadge(match.away_team));
  const middle = el("span", "hero-score", match.status === "played" ? `${match.home_goals}–${match.away_goals}` : "v");
  title.replaceChildren(home, middle, away);
  document.getElementById("match-meta").textContent =
    `Matchday ${match.matchday} · ${formatDate(match.date)}` + (match.status === "played" ? " · Full time" : match.time ? ` · ${match.time} kick-off (Italian time)` : "");
  document.title = `${match.home_team} v ${match.away_team} · Serie A Analytics`;
}

function predictionBlock(match) {
  const p = probs(match, MAIN);
  if (!p) return el("p", "muted", "Prediction not available.");
  const happened = match.status === "played" ? RESULT_TO_OUTCOME[match.result] : null;
  const box = el("div", "match");
  box.append(el("div", "forecast-title", "Our prediction"), probabilityBar(p, match, "Our prediction", happened, { big: true }), verdict(match, p, happened));
  return box;
}

function scorersBlock(match, scorers) {
  if (!scorers) {
    const total = match.home_goals + match.away_goals;
    return el("p", "muted", total === 0 ? "No goals." : "Goalscorers not available yet: they appear once our open data source adds them.");
  }
  const grid = el("div", "scorers");
  for (const side of ["home", "away"]) {
    const col = el("div", `scorers-col ${side}`);
    col.append(el("div", "scorers-team", match[`${side}_team`]));
    const byPlayer = new Map();
    for (const g of scorers[side]) {
      const label = `${g.minute}'${g.penalty ? " (pen)" : ""}${g.own_goal ? " (og)" : ""}`;
      byPlayer.set(g.player, [...(byPlayer.get(g.player) ?? []), label]);
    }
    if (!byPlayer.size) col.append(el("div", "muted small", "–"));
    for (const [player, minutes] of byPlayer) col.append(el("div", "scorer", `⚽ ${player} ${minutes.join(", ")}`));
    grid.append(col);
  }
  return grid;
}

function statsBlock(match, stats) {
  const table = el("div", "stat-compare");
  const head = el("div", "stat-row head");
  head.append(el("span", "", match.home_team), el("span", ""), el("span", "", match.away_team));
  table.append(head);
  for (const [label, key, decimals] of STAT_ROWS) {
    const h = stats[`home_${key}`], a = stats[`away_${key}`];
    if (h === null || a === null || h === undefined) continue;
    const row = el("div", "stat-row");
    const bar = el("div", "stat-bar");
    const total = h + a;
    const left = el("span", "home"), right = el("span", "away");
    left.style.flexGrow = total ? h : 1;
    right.style.flexGrow = total ? a : 1;
    bar.append(left, right);
    const middle = el("div", "stat-label");
    middle.append(el("span", "", label), bar);
    row.append(el("strong", "", h.toFixed(decimals)), middle, el("strong", "", a.toFixed(decimals)));
    table.append(row);
  }
  return table;
}

function topScoresBlock(match) {
  const scores = match.dc_top_scores;
  const wrap = el("div", "top-scores");
  for (const [h, a, p] of scores ?? []) {
    const chip = el("div", "score-chip");
    chip.append(el("strong", "", `${h}–${a}`), el("span", "", percent(p)));
    wrap.append(chip);
  }
  const facts = el("div", "facts");
  const add = (label, value) => {
    const item = el("span", "", `${label} `);
    item.append(el("strong", "", value));
    facts.append(item);
  };
  if (match.dc_xg_home !== null) add("Expected goals", `${match.dc_xg_home.toFixed(1)}–${match.dc_xg_away.toFixed(1)}`);
  if (match.dc_over_2_5 !== null) add("Over 2.5 goals", percent(match.dc_over_2_5));
  if (match.dc_btts !== null) add("Both teams score", percent(match.dc_btts));
  return [wrap, facts];
}

function formBlock(match, matches) {
  const wrap = el("div", "form-compare");
  for (const team of [match.home_team, match.away_team]) {
    const games = matches
      .filter((m) => m.status === "played" && m.date < match.date && (m.home_team === team || m.away_team === team))
      .slice(-5);
    const row = el("div", "form-team");
    row.append(teamLink(team));
    const chips = el("div", "form-row");
    for (const m of games) {
      const scored = m.home_team === team ? m.home_goals : m.away_goals;
      const conceded = m.home_team === team ? m.away_goals : m.home_goals;
      const r = scored > conceded ? "W" : scored === conceded ? "D" : "L";
      const chip = el("span", `form-chip small ${r}`, r);
      chip.dataset.tip = `${m.home_team} ${m.home_goals}–${m.away_goals} ${m.away_team}`;
      chips.append(chip);
    }
    if (!games.length) chips.append(el("span", "muted small", "No games yet"));
    row.append(chips);
    wrap.append(row);
  }
  return wrap;
}

function h2hBlock(h2h) {
  if (!h2h.length) return el("p", "muted", "These two teams haven't met in Serie A since 2005.");
  const list = el("ul", "results");
  for (const g of h2h) {
    list.append(el("li", "", `${formatDate(g.date)} ${g.date.slice(0, 4)} · ${g.home_team} ${g.home_goals}–${g.away_goals} ${g.away_team}`));
  }
  return list;
}

async function main() {
  enableTooltips();
  try {
    const [summary, matches, details] = await Promise.all([loadData("summary"), loadData("matches"), loadData("match_details")]);
    document.getElementById("updated").textContent = `Updated ${formatDate(summary.generated_at.slice(0, 10))}.`;
    const id = new URLSearchParams(location.search).get("id");
    const match = matches.find((m) => m.match_id === id);
    const main = document.getElementById("match-main");
    if (!match) {
      document.getElementById("match-title").textContent = "Match not found";
      main.replaceChildren(el("p", "", "This match isn't in the current season. "), Object.assign(el("a", "", "Back to the matches"), { href: "./" }));
      return;
    }
    const info = details[id] ?? { h2h: [] };
    renderHero(match);
    if (match.status === "played") {
      main.append(
        section("Match report", el("p", "report", info.report ?? "")),
        section("Goals", scorersBlock(match, info.scorers)),
        section("Our prediction", predictionBlock(match)),
        section("Match stats", statsBlock(match, info.stats ?? {})),
      );
    } else {
      main.append(
        section("Our prediction", predictionBlock(match)),
        section("Most likely scores", ...topScoresBlock(match)),
        section("Form", formBlock(match, matches)),
      );
    }
    main.append(section("Last meetings", h2hBlock(info.h2h)));
    const back = el("a", "back-link", `← All Matchday ${match.matchday} matches`);
    back.href = `./#matchday-${match.matchday}`;
    main.append(back);
  } catch (error) {
    showError(document.querySelector("main"), error);
  }
}

main();
