// Profile revamp: official WoW class colours, used as an accent for class cards and
// character avatars. Keys are the CLASS_SPECS filter values (wcl_agent/constants.py),
// normalised so "DeathKnight", "Death Knight" and "deathknight" all resolve.

const CLASS_COLORS: Record<string, string> = {
  deathknight: "#C41E3A",
  demonhunter: "#A330C9",
  druid: "#FF7C0A",
  evoker: "#33937F",
  hunter: "#AAD372",
  mage: "#3FC7EB",
  monk: "#00FF98",
  paladin: "#F48CBA",
  priest: "#FFFFFF",
  rogue: "#FFF468",
  shaman: "#0070DD",
  warlock: "#8788EE",
  warrior: "#C69B6D",
};

function normalise(className: string): string {
  return className.toLowerCase().replace(/[^a-z]/g, "");
}

/** The class colour, or null for an unknown / missing class (callers fall back to theme tokens). */
export function classColor(className: string | null | undefined): string | null {
  if (!className) return null;
  return CLASS_COLORS[normalise(className)] ?? null;
}

/** One or two initials for an avatar fallback, e.g. "Thrall" → "T", "Jaina Proudmoore" → "JP". */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

/** "DeathKnight" → "Death Knight"; display names that already have spaces pass through. */
export function classDisplayName(className: string): string {
  return className.replace(/([a-z])([A-Z])/g, "$1 $2");
}
