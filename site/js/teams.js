// Mini kit shirts shown next to team names: each club's traditional home shirt design.
// These are drawn by us from the shirt colours and pattern, not club logos or crests
// (those are trademarks).

// pattern: "stripes" (vertical), "halves" (left/right), "plain" (with a coloured collar),
// "trim" (collar and sleeve cuffs), "cross" (Parma), "band" (a chest band, Sampdoria)
export const KITS = {
  Atalanta: { pattern: "stripes", base: "#111111", detail: "#1b5ea8" },
  Bologna: { pattern: "halves", base: "#a3162b", detail: "#1a2f5a" },
  Cagliari: { pattern: "halves", base: "#a3162b", detail: "#1a2f5a" },
  Como: { pattern: "plain", base: "#1c4c9c", detail: "#ffffff" },
  Cremonese: { pattern: "stripes", base: "#8a8d8f", detail: "#b01e2e" },
  Empoli: { pattern: "plain", base: "#1d5bbf", detail: "#ffffff" },
  Fiorentina: { pattern: "trim", base: "#5b2d8e", detail: "#ffffff" },
  Frosinone: { pattern: "trim", base: "#f2c500", detail: "#1a3b8f" },
  Genoa: { pattern: "halves", base: "#a3162b", detail: "#1a2f5a" },
  Inter: { pattern: "stripes", base: "#111111", detail: "#0a4fa3" },
  Juventus: { pattern: "stripes", base: "#ffffff", detail: "#111111" },
  Lazio: { pattern: "trim", base: "#8fc8ee", detail: "#ffffff" },
  Lecce: { pattern: "stripes", base: "#f2c500", detail: "#c8102e" },
  Milan: { pattern: "stripes", base: "#111111", detail: "#c8102e" },
  Monza: { pattern: "trim", base: "#c8102e", detail: "#ffffff" },
  Napoli: { pattern: "plain", base: "#1e8fd6", detail: "#ffffff" },
  Parma: { pattern: "cross", base: "#ffffff", detail: "#111111" },
  Pisa: { pattern: "stripes", base: "#111111", detail: "#1a3b8f" },
  Roma: { pattern: "trim", base: "#8e1f2f", detail: "#f0a500" },
  Salernitana: { pattern: "plain", base: "#6d1a2a", detail: "#ffffff" },
  Sampdoria: { pattern: "band", base: "#1d4fa0", detail: "#ffffff" },
  Sassuolo: { pattern: "stripes", base: "#111111", detail: "#00873e" },
  Spezia: { pattern: "trim", base: "#ffffff", detail: "#111111" },
  Torino: { pattern: "trim", base: "#7a1d2a", detail: "#ffffff" },
  Udinese: { pattern: "stripes", base: "#ffffff", detail: "#111111" },
  Venezia: { pattern: "trim", base: "#111111", detail: "#f26a1b" },
  Verona: { pattern: "trim", base: "#1a3b8f", detail: "#f2c500" },
};

// The shirt outline, in a 44 x 42 drawing
const SHIRT = "M13 4 L4 10 L7 17 L11 15 L11 38 L33 38 L33 15 L37 17 L40 10 L31 4 Q22 10 13 4 Z";
const COLLAR = "M13 4 Q22 10 31 4 L31 7 Q22 13 13 7 Z";
const SVG_NS = "http://www.w3.org/2000/svg";
let nextId = 0; // each shirt needs its own clip-path id on the page

/** The coloured shapes inside the shirt, for one pattern. */
function patternShapes({ pattern, base, detail }) {
  const rect = (x, y, w, h, fill) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}"/>`;
  let shapes = rect(0, 0, 44, 42, base);
  if (pattern === "stripes") shapes += [11, 21, 31].map((x) => rect(x, 0, 5, 42, detail)).join("");
  if (pattern === "halves") shapes += rect(22, 0, 22, 42, detail);
  if (pattern === "plain") shapes += `<path d="${COLLAR}" fill="${detail}"/>`;
  if (pattern === "trim") shapes += `<path d="${COLLAR}" fill="${detail}"/>` + rect(0, 10, 11, 3, detail) + rect(33, 10, 11, 3, detail);
  if (pattern === "cross") shapes += rect(19, 0, 6, 42, detail) + rect(0, 17, 44, 6, detail);
  if (pattern === "band") shapes += rect(0, 18, 44, 3, detail) + rect(0, 21, 44, 2, "#c8102e") + rect(0, 23, 44, 2, "#111111") + rect(0, 25, 44, 3, detail);
  return shapes;
}

/** A small shirt in the team's colours (plain grey if we don't know the club). */
export function kitBadge(team) {
  const kit = KITS[team] ?? { pattern: "plain", base: "#9a9a9a", detail: "#d0d0d0" };
  const id = `kit-${nextId++}`;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 44 42");
  svg.setAttribute("class", "kit");
  svg.setAttribute("aria-hidden", "true"); // decoration only; the team name is written next to it
  svg.innerHTML =
    `<clipPath id="${id}"><path d="${SHIRT}"/></clipPath>` +
    `<g clip-path="url(#${id})">${patternShapes(kit)}</g>` +
    `<path class="kit-outline" d="${SHIRT}" fill="none" stroke-width="1.4"/>`; // colour set in the CSS (light/dark)
  return svg;
}
