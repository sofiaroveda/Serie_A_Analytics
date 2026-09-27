// The matchday strip: a swipeable row of chips, one per matchday.
// Used by the Matches page and the Data lab page.
import { el } from "./common.js";

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
function matchdayDates(matches, n) {
  const dates = matches.filter((m) => m.matchday === n).map((m) => m.date).sort();
  if (!dates.length) return "";
  const middle = new Date(dates[Math.floor(dates.length / 2)]);
  const near = dates.filter((d) => Math.abs(new Date(d) - middle) <= 4 * 86_400_000);
  return shortRange(near[0], near[near.length - 1]);
}

/**
 * Build the strip inside #md-scroller (with #prev / #next arrows) and show a matchday.
 * `onShow(n)` is called whenever matchday n is chosen. The choice is kept in the
 * page address (e.g. #matchday-4) so links can point at a specific matchday.
 */
export function setUpStrip({ matches, total, next, onShow }) {
  const fromUrl = () => {
    const found = location.hash.match(/^#matchday-(\d+)$/);
    const n = found ? Number(found[1]) : null;
    return n >= 1 && n <= total ? n : null;
  };

  const scroller = document.getElementById("md-scroller");
  const chips = [];
  for (let n = 1; n <= total; n++) {
    const dates = matchdayDates(matches, n);
    const chip = el("button", `md-chip${n === next ? " is-next" : ""}`);
    chip.type = "button";
    chip.append(el("span", "md-num", `MD ${n}`), el("span", "md-dates", n === next ? `Next · ${dates}` : dates));
    chip.setAttribute("aria-label", `Matchday ${n}, ${dates}${n === next ? ", next to be played" : ""}`);
    chip.addEventListener("click", () => show(n));
    scroller.append(chip);
    chips.push(chip);
  }

  let current = next;
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
    document.getElementById("next").disabled = n >= total;
    history.replaceState(null, "", `#matchday-${n}`); // update the address without reloading
    onShow(n);
  }

  document.getElementById("prev").addEventListener("click", () => show(current - 1));
  document.getElementById("next").addEventListener("click", () => show(current + 1));
  window.addEventListener("hashchange", () => fromUrl() && show(fromUrl()));
  show(fromUrl() ?? next, false);
}
