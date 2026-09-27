// Each club's kit colours [primary, secondary], used for the small badges next to team names.
// These are just the traditional shirt colours, not club logos or crests (those are trademarks).
export const KIT_COLOURS = {
  Atalanta: ["#1b5ea8", "#111111"],
  Bologna: ["#a3162b", "#1a2f5a"],
  Cagliari: ["#a3162b", "#1a2f5a"],
  Como: ["#1c4c9c", "#ffffff"],
  Cremonese: ["#b01e2e", "#8a8d8f"],
  Empoli: ["#1d5bbf", "#ffffff"],
  Fiorentina: ["#5b2d8e", "#ffffff"],
  Frosinone: ["#f2c500", "#1a3b8f"],
  Genoa: ["#a3162b", "#1a2f5a"],
  Inter: ["#0a4fa3", "#111111"],
  Juventus: ["#111111", "#ffffff"],
  Lazio: ["#8fc8ee", "#ffffff"],
  Lecce: ["#f2c500", "#c8102e"],
  Milan: ["#c8102e", "#111111"],
  Monza: ["#c8102e", "#ffffff"],
  Napoli: ["#1e8fd6", "#ffffff"],
  Parma: ["#f2c500", "#1a3b8f"],
  Pisa: ["#111111", "#1a3b8f"],
  Roma: ["#8e1f2f", "#f0a500"],
  Salernitana: ["#6d1a2a", "#ffffff"],
  Sampdoria: ["#1d4fa0", "#ffffff"],
  Sassuolo: ["#00873e", "#111111"],
  Spezia: ["#ffffff", "#111111"],
  Torino: ["#7a1d2a", "#ffffff"],
  Udinese: ["#111111", "#ffffff"],
  Venezia: ["#f26a1b", "#0f7a3d"],
  Verona: ["#f2c500", "#1a3b8f"],
};

/** A small round badge split into the team's two kit colours (grey if unknown). */
export function kitBadge(team) {
  const [a, b] = KIT_COLOURS[team] ?? ["#9a9a9a", "#d0d0d0"];
  const badge = document.createElement("span");
  badge.className = "kit";
  badge.style.background = `linear-gradient(135deg, ${a} 0 50%, ${b} 50% 100%)`;
  badge.setAttribute("aria-hidden", "true"); // decoration only; the team name is written next to it
  return badge;
}
