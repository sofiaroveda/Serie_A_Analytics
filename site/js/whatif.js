// "What if?" simulator (Table page): pick results of upcoming matches, and the rest of the
// season is re-simulated in the browser, the same way as the Python simulation
// (pipeline/simulate.py): expected goals from our goals model, a random strength shock
// per team per simulated season, Poisson goals, ranking by points, goal difference, goals scored.
import { el, percent, formatDate } from "./common.js";
import { kitBadge } from "./teams.js";
import { price, changeBadge, teamLink } from "./stocks.js";

const N_SIMS = 10_000;
const SEED = 20260827;

// ---------- Random numbers (seeded, so the same picks always give the same answer) ----------

/** A small, fast seeded random number generator (mulberry32): returns numbers in [0, 1). */
function seededRandom(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A standard normal draw (Box-Muller). */
function normal(rand) {
  return Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
}

/** A Poisson draw with mean `mean` (Knuth's method: fine for football-sized means). */
function poisson(mean, rand) {
  const limit = Math.exp(-mean);
  let k = 0;
  let p = rand();
  while (p > limit) {
    k++;
    p *= rand();
  }
  return k;
}

const outcomeOf = (home, away) => (home > away ? "H" : home === away ? "D" : "A");

/**
 * League order, best first, by Serie A's rules (same as pipeline/tiebreak.py): points, then for
 * teams level on points their head-to-head points and goal difference, then overall goal
 * difference, goals scored, and lots. A two-team tie for first place or across the relegation
 * line is a play-off, settled here by a coin toss (`coin`).
 * matchHome/matchAway/matchHG/matchAG list every match of the season (played and simulated).
 */
function orderTeams(n, points, gf, ga, lots, matchHome, matchAway, matchHG, matchAG, coin) {
  const order = [...Array(n).keys()].sort((x, y) =>
    points[y] - points[x] || (gf[y] - ga[y]) - (gf[x] - ga[x]) || gf[y] - gf[x] || lots[y] - lots[x]);
  const ranked = [];
  const safePlaces = n - 3;
  for (let i = 0; i < n;) {
    let j = i;
    while (j + 1 < n && points[order[j + 1]] === points[order[i]]) j++;
    const group = order.slice(i, j + 1);
    if (group.length > 1) {
      const inGroup = new Set(group);
      const h2hPoints = new Array(n).fill(0), h2hGd = new Array(n).fill(0);
      for (let k = 0; k < matchHome.length; k++) {
        const h = matchHome[k], a = matchAway[k];
        if (!inGroup.has(h) || !inGroup.has(a)) continue;
        const hg = matchHG[k], ag = matchAG[k];
        h2hGd[h] += hg - ag;
        h2hGd[a] += ag - hg;
        if (hg > ag) h2hPoints[h] += 3;
        else if (hg < ag) h2hPoints[a] += 3;
        else { h2hPoints[h] += 1; h2hPoints[a] += 1; }
      }
      group.sort((x, y) => h2hPoints[y] - h2hPoints[x] || h2hGd[y] - h2hGd[x]
        || (gf[y] - ga[y]) - (gf[x] - ga[x]) || gf[y] - gf[x] || lots[y] - lots[x]);
      const crossesLine = i === 0 || (i < safePlaces && safePlaces <= j);
      if (group.length === 2 && crossesLine && coin() < 0.5) group.reverse(); // the play-off
    }
    ranked.push(...group);
    i = j + 1;
  }
  return ranked;
}

// ---------- The simulation ----------

/**
 * Simulate the rest of the season.
 * teams: names; table: current rows {team, points, goals_for, goals_against};
 * played: this season's results [{home, away, homeGoals, awayGoals}] (for head-to-head tie-breaks);
 * fixtures: [{id, home, away, lam, mu}]; picks: {id: "H" | "D" | "A"}; sd: strength uncertainty.
 * Returns {team: {title, top4, europe, relegation, expPoints}}.
 *
 * Every simulated season uses the same random numbers whatever the picks (a picked match
 * that comes out differently is redrawn from a separate stream), so comparing "with picks"
 * against "without picks" shows the effect of the picks, not random noise.
 */
export function simulate({ teams, table, played = [], fixtures, picks, sd, nSims = N_SIMS }) {
  const n = teams.length;
  const index = Object.fromEntries(teams.map((t, i) => [t, i]));
  const base = { points: new Array(n).fill(0), gf: new Array(n).fill(0), ga: new Array(n).fill(0) };
  for (const row of table) {
    const i = index[row.team];
    base.points[i] = row.points;
    base.gf[i] = row.goals_for;
    base.ga[i] = row.goals_against;
  }
  const home = fixtures.map((f) => index[f.home]);
  const away = fixtures.map((f) => index[f.away]);
  const pick = fixtures.map((f) => picks[f.id] ?? null);

  const counts = { title: new Array(n).fill(0), top4: new Array(n).fill(0), europe: new Array(n).fill(0), relegation: new Array(n).fill(0), points: new Array(n).fill(0) };
  const rand = seededRandom(SEED);
  const redraw = seededRandom(SEED + 1); // only used to redraw picked matches
  const coin = seededRandom(SEED + 2); // only used for play-offs
  const points = new Array(n), gf = new Array(n), ga = new Array(n), shock = new Array(n), tiebreak = new Array(n);

  // Every match of the season, for head-to-head: played results first, then this simulation's scores
  const P = played.length, F = fixtures.length;
  const matchHome = [...played.map((m) => index[m.home]), ...home];
  const matchAway = [...played.map((m) => index[m.away]), ...away];
  const matchHG = [...played.map((m) => m.homeGoals), ...new Array(F).fill(0)];
  const matchAG = [...played.map((m) => m.awayGoals), ...new Array(F).fill(0)];

  for (let s = 0; s < nSims; s++) {
    for (let i = 0; i < n; i++) {
      points[i] = base.points[i];
      gf[i] = base.gf[i];
      ga[i] = base.ga[i];
      shock[i] = normal(rand) * sd;
    }
    for (let f = 0; f < fixtures.length; f++) {
      const h = home[f], a = away[f];
      const lam = fixtures[f].lam * Math.exp(shock[h] - shock[a]);
      const mu = fixtures[f].mu * Math.exp(shock[a] - shock[h]);
      let hg = poisson(lam, rand);
      let ag = poisson(mu, rand);
      if (pick[f] && outcomeOf(hg, ag) !== pick[f]) {
        // Redraw until the score matches the pick (a likely scoreline for that result)
        let tries = 0;
        do {
          hg = poisson(lam, redraw);
          ag = poisson(mu, redraw);
        } while (outcomeOf(hg, ag) !== pick[f] && ++tries < 500);
        if (outcomeOf(hg, ag) !== pick[f]) [hg, ag] = pick[f] === "H" ? [1, 0] : pick[f] === "A" ? [0, 1] : [1, 1];
      }
      gf[h] += hg; ga[h] += ag; gf[a] += ag; ga[a] += hg;
      matchHG[P + f] = hg;
      matchAG[P + f] = ag;
      if (hg > ag) points[h] += 3;
      else if (hg < ag) points[a] += 3;
      else { points[h] += 1; points[a] += 1; }
    }
    for (let i = 0; i < n; i++) tiebreak[i] = rand();
    const order = orderTeams(n, points, gf, ga, tiebreak, matchHome, matchAway, matchHG, matchAG, coin);
    order.forEach((t, place) => {
      if (place === 0) counts.title[t]++;
      if (place < 4) counts.top4[t]++;
      if (place < 6) counts.europe[t]++;
      if (place >= n - 3) counts.relegation[t]++;
    });
    for (let i = 0; i < n; i++) counts.points[i] += points[i];
  }

  return Object.fromEntries(teams.map((t, i) => [t, {
    title: counts.title[i] / nSims, top4: counts.top4[i] / nSims, europe: counts.europe[i] / nSims,
    relegation: counts.relegation[i] / nSims, expPoints: counts.points[i] / nSims,
  }]));
}

// ---------- The page ----------

/** Set up the What if? tab. Called once, the first time the tab is opened. */
export function setUpWhatIf({ matches, table, simulation }) {
  const upcoming = matches.filter((m) => m.status === "upcoming" && m.dc_xg_home !== null);
  const fixtures = upcoming.map((m) => ({ id: m.match_id, home: m.home_team, away: m.away_team, lam: m.dc_xg_home, mu: m.dc_xg_away }));
  const teams = [...new Set([...table.map((r) => r.team), ...matches.flatMap((m) => [m.home_team, m.away_team])])];
  const played = matches.filter((m) => m.status === "played")
    .map((m) => ({ home: m.home_team, away: m.away_team, homeGoals: m.home_goals, awayGoals: m.away_goals }));
  const picks = {};
  const run = () => simulate({ teams, table, played, fixtures, picks, sd: simulation.strength_sd });

  const baseline = run(); // no picks: the model decides every match
  renderPicker(upcoming, picks, () => update());
  const results = document.getElementById("whatif-results");
  const status = document.getElementById("whatif-status");
  let pending = null;

  function update() {
    status.textContent = "Simulating…";
    clearTimeout(pending);
    // Let the page repaint first, so the buttons respond instantly
    pending = setTimeout(() => {
      const scenario = run();
      renderResults(results, baseline, scenario, Object.keys(picks).length);
      renderSummary(baseline, scenario, Object.keys(picks).length);
      const n = Object.keys(picks).length;
      status.textContent = n ? `${n} result${n === 1 ? "" : "s"} picked · ${N_SIMS.toLocaleString("en-GB")} simulated seasons` : "No results picked yet";
      document.getElementById("whatif-reset").hidden = n === 0;
    }, 30);
  }
  document.getElementById("whatif-reset").addEventListener("click", () => {
    for (const id of Object.keys(picks)) delete picks[id];
    document.querySelectorAll(".pick button[aria-pressed='true']").forEach((b) => b.setAttribute("aria-pressed", "false"));
    update();
  });
  update();
}

function renderPicker(upcoming, picks, onChange) {
  const container = document.getElementById("whatif-picker");
  const byMatchday = new Map();
  for (const m of upcoming) {
    if (!byMatchday.has(m.matchday)) byMatchday.set(m.matchday, []);
    byMatchday.get(m.matchday).push(m);
  }
  let first = true;
  for (const [matchday, games] of byMatchday) {
    const group = el("details", "whatif-md");
    group.open = first; // the next matchday starts open; later ones are one tap away
    first = false;
    group.append(el("summary", "", `Matchday ${matchday} · ${formatDate(games[0].date)}`));
    for (const m of games) group.append(pickRow(m, picks, onChange));
    container.append(group);
  }
}

function pickRow(m, picks, onChange) {
  const row = el("div", "pick");
  const options = [
    ["H", m.home_team, m.dc_home, kitBadge(m.home_team)],
    ["D", "Draw", m.dc_draw, null],
    ["A", m.away_team, m.dc_away, kitBadge(m.away_team)],
  ];
  const buttons = [];
  for (const [outcome, label, p, badge] of options) {
    const button = el("button", `pick-${outcome}`);
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    const name = el("span", "pick-name");
    if (badge) name.append(badge);
    name.append(label);
    button.append(name, el("span", "pick-chance", percent(p)));
    button.title = outcome === "D" ? `Pick a draw (we give it ${percent(p)})` : `Pick a ${label} win (we give it ${percent(p)})`;
    button.addEventListener("click", () => {
      const already = picks[m.match_id] === outcome;
      if (already) delete picks[m.match_id];
      else picks[m.match_id] = outcome;
      buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(!already && options[i][0] === outcome)));
      onChange();
    });
    buttons.push(button);
    row.append(button);
  }
  return row;
}

/** Phones: title race (top two) and the most likely to go down, pinned to the bottom of the screen. */
function renderSummary(baseline, scenario, nPicks) {
  const bar = document.getElementById("whatif-summary");
  bar.hidden = nPicks === 0;
  if (!nPicks) return;
  const byTitle = Object.keys(scenario).sort((a, b) => scenario[b].title - scenario[a].title);
  const byDrop = Object.keys(scenario).sort((a, b) => scenario[b].relegation - scenario[a].relegation);
  const item = (team, key, goodIfUp) => {
    const span = el("span", "summary-item", `${team} ${price(scenario[team][key])} `);
    span.append(changeBadge(baseline[team][key], scenario[team][key], goodIfUp, "because of your picks"));
    return span;
  };
  bar.replaceChildren(
    el("span", "summary-label", "Title"), item(byTitle[0], "title", true), item(byTitle[1], "title", true),
    el("span", "summary-label", "Down"), item(byDrop[0], "relegation", false),
    el("span", "summary-more", "Full table ↓"),
  );
  bar.onclick = () => document.getElementById("whatif-results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderResults(container, baseline, scenario, nPicks) {
  const teams = Object.keys(scenario).sort((a, b) => scenario[b].expPoints - scenario[a].expPoints || scenario[b].title - scenario[a].title);
  const body = container.querySelector("tbody");
  body.replaceChildren();
  teams.forEach((team, i) => {
    const now = scenario[team];
    const before = baseline[team];
    const row = el("tr");
    const name = el("td", "team");
    name.append(teamLink(team));
    row.append(el("td", "pos", i + 1), name, el("td", "pts", Math.round(now.expPoints)));
    for (const [key, goodIfUp] of [["title", true], ["top4", true], ["relegation", false]]) {
      const cell = el("td", "whatif-cell", price(now[key]));
      if (nPicks && Math.round(now[key] * 100) !== Math.round(before[key] * 100)) {
        cell.append(changeBadge(before[key], now[key], goodIfUp, "because of your picks"));
      }
      row.append(cell);
    }
    body.append(row);
  });
}
