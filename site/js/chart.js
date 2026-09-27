// Small SVG charts for the market: a price line chart and a sparkline.
// Drawn by hand (no chart library) so they share the site's colours and tooltip.

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

/** A 0-100% scale that fits the data with a little headroom (so small chances aren't squashed flat). */
function niceTop(maxValue) {
  for (const top of [0.1, 0.25, 0.5, 0.75, 1]) if (maxValue <= top * 0.95) return top;
  return 1;
}

/**
 * Line chart of a probability over the season.
 * points: [{ label: "MD 3", value: 0.23, tip: "text for the tooltip" }, ...]
 * colour: a CSS colour (e.g. "var(--accent)"); width: the width in pixels it will be shown at.
 */
export function priceChart(points, { colour = "var(--accent)", width = 640, height = 220 } = {}) {
  // Drawn at the width it will be shown at, so the labels stay readable on phones
  const pad = { top: 14, right: 16, bottom: 28, left: 40 };
  const top = niceTop(Math.max(...points.map((p) => p.value), 0.01));
  const x = (i) => pad.left + (points.length === 1 ? 0.5 : i / (points.length - 1)) * (width - pad.left - pad.right);
  const y = (v) => pad.top + (1 - v / top) * (height - pad.top - pad.bottom);

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "price-chart", role: "img" });
  svg.setAttribute("aria-label", points.map((p) => `${p.label}: ${Math.round(p.value * 100)}%`).join(", "));

  // Gridlines and y labels (recessive), at round steps: 0/25/50/75/100% or 0/5/10...%
  const step = top <= 0.25 ? 0.05 : 0.25;
  for (let v = 0; v <= top + 1e-9; v += step) {
    svg.append(svgEl("line", { x1: pad.left, x2: width - pad.right, y1: y(v), y2: y(v), class: "grid" }));
    const label = svgEl("text", { x: pad.left - 8, y: y(v) + 4, "text-anchor": "end", class: "axis-label" });
    label.textContent = `${Math.round(v * 100)}%`;
    svg.append(label);
  }
  // X labels: first, last and a few in between
  const every = Math.max(1, Math.ceil(points.length / 7));
  points.forEach((p, i) => {
    if (i % every && i !== points.length - 1) return;
    const label = svgEl("text", { x: x(i), y: height - 8, "text-anchor": "middle", class: "axis-label" });
    label.textContent = p.label;
    svg.append(label);
  });

  // Shaded area under the line, then the line, then the points (with tooltips)
  const line = points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ");
  svg.append(svgEl("polygon", {
    points: `${x(0)},${y(0)} ${line} ${x(points.length - 1)},${y(0)}`,
    fill: colour, "fill-opacity": "0.12",
  }));
  svg.append(svgEl("polyline", { points: line, fill: "none", stroke: colour, "stroke-width": 2.5, "stroke-linejoin": "round" }));
  points.forEach((p, i) => {
    const hit = svgEl("circle", { cx: x(i), cy: y(p.value), r: 12, fill: "transparent", class: "hit" });
    hit.dataset.tip = p.tip ?? `${p.label}: ${Math.round(p.value * 100)}%`;
    const dot = svgEl("circle", { cx: x(i), cy: y(p.value), r: i === points.length - 1 ? 5 : 3.5, fill: colour, class: "dot" });
    svg.append(dot, hit);
  });
  return svg;
}

/** A tiny trend line for tables. `values` are probabilities, oldest first. */
export function sparkline(values, { colour = "var(--accent)", width = 84, height = 26 } = {}) {
  const top = niceTop(Math.max(...values, 0.01));
  const x = (i) => 2 + (values.length === 1 ? 0.5 : i / (values.length - 1)) * (width - 4);
  const y = (v) => 3 + (1 - v / top) * (height - 6);
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "sparkline", "aria-hidden": "true" });
  svg.append(svgEl("polyline", {
    points: values.map((v, i) => `${x(i)},${y(v)}`).join(" "),
    fill: "none", stroke: colour, "stroke-width": 2, "stroke-linejoin": "round",
  }));
  svg.append(svgEl("circle", { cx: x(values.length - 1), cy: y(values[values.length - 1]), r: 2.5, fill: colour }));
  return svg;
}
