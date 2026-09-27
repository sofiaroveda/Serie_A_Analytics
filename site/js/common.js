// Shared helpers used by every page. Each page's own script imports what it needs:
//   import { loadData, probabilityBar } from "./common.js";

/** Fetch one of the JSON files the Python pipeline writes to site/data/. */
export async function loadData(name) {
  const response = await fetch(`data/${name}.json`);
  if (!response.ok) throw new Error(`Could not load data/${name}.json (${response.status})`);
  return response.json();
}

/** "2026-09-20" -> "Sun 20 Sep" */
export function formatDate(isoDate) {
  const date = new Date(`${isoDate}T12:00:00`);
  return date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

/** 0.4567 -> "46%" */
export function percent(p) {
  return `${Math.round(p * 100)}%`;
}

/** Create an element with optional class and text, e.g. el("p", "muted", "Hello"). */
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const OUTCOME_NAMES = { home: "Home win", draw: "Draw", away: "Away win" };

/**
 * A horizontal bar split into home / draw / away segments.
 * `match` needs p_home, p_draw, p_away and team names; `happened` is
 * "home" | "draw" | "away" for played matches (that segment gets outlined).
 */
export function probabilityBar(match, happened) {
  const bar = el("div", "prob-bar");
  bar.setAttribute("role", "img");
  bar.setAttribute(
    "aria-label",
    `Market probabilities: ${match.home_team} win ${percent(match.p_home)}, ` +
      `draw ${percent(match.p_draw)}, ${match.away_team} win ${percent(match.p_away)}`
  );

  for (const outcome of ["home", "draw", "away"]) {
    const p = match[`p_${outcome}`];
    const seg = el("div", `prob-seg ${outcome}`);
    seg.style.flexGrow = p; // segment width is proportional to the probability
    seg.style.flexBasis = "0";
    if (p >= 0.1) seg.textContent = percent(p); // only label segments wide enough to fit text
    if (outcome === happened) seg.classList.add("happened");

    const team = outcome === "home" ? match.home_team : outcome === "away" ? match.away_team : null;
    const name = team ? `${team} win` : OUTCOME_NAMES[outcome];
    seg.dataset.tip = `${name}: ${percent(p)}${outcome === happened ? " (what happened)" : ""}`;
    bar.append(seg);
  }
  return bar;
}

/** Legend explaining the bar colours. */
export function outcomeLegend() {
  const legend = el("div", "legend");
  for (const outcome of ["home", "draw", "away"]) {
    const item = el("span");
    const swatch = el("span", "swatch");
    swatch.style.background = `var(--${outcome})`;
    item.append(swatch, OUTCOME_NAMES[outcome]);
    legend.append(item);
  }
  return legend;
}

/** One small tooltip, shown when hovering any element that has a data-tip attribute. */
export function enableTooltips() {
  const tip = el("div", "tooltip");
  tip.hidden = true;
  document.body.append(tip);

  document.addEventListener("pointermove", (event) => {
    const target = event.target.closest?.("[data-tip]");
    if (!target) {
      tip.hidden = true;
      return;
    }
    tip.textContent = target.dataset.tip;
    tip.hidden = false;
    const x = Math.min(event.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = `${x}px`;
    tip.style.top = `${event.clientY + 16}px`;
  });
  document.addEventListener("scroll", () => (tip.hidden = true), { passive: true });
}

/** Show an error message in place of content if data fails to load. */
export function showError(container, error) {
  container.replaceChildren(el("p", "empty", `Sorry, the data could not be loaded. ${error.message}`));
  console.error(error);
}
