// US6 spell registry: one entry per real agent tool, so every tool call feels
// distinct (icon, magic-school hue, verb, rotating flavor lines). Every tool the
// agent exposes (16 WCL tools + web_search) MUST be mapped; unknown/new tools fall
// back to DEFAULT_SPELL so a card never renders blank or crashes (FR-031).
// Icons are from react-icons/gi (game-icons.net, CC BY 3.0 — see the app footer).

import type { IconType } from "react-icons";
import {
  GiBarbedSun,
  GiBattleGear,
  GiBleedingWound,
  GiChart,
  GiCrossedSwords,
  GiCrystalBall,
  GiHealthPotion,
  GiHistogram,
  GiHourglass,
  GiMagicSwirl,
  GiMagnifyingGlass,
  GiPerson,
  GiPodium,
  GiScrollQuill,
  GiScrollUnfurled,
  GiSpellBook,
  GiStoneTablet,
  GiTrophy,
} from "react-icons/gi";

export interface Spell {
  icon: IconType;
  hue: string;
  verb: string;
  flavor: string[];
}

const GOLD = "oklch(0.82 0.16 85)";
const SCRY_BLUE = "oklch(0.78 0.14 220)";
const ARCANE = "oklch(0.75 0.20 300)";
const EMBER = "oklch(0.72 0.18 50)";
const VERDANT = "oklch(0.78 0.18 140)";
const CRIMSON = "oklch(0.64 0.20 25)";

export const SPELLS: Record<string, Spell> = {
  // --- Leaderboard / population ---
  get_selected_encounter: {
    icon: GiBarbedSun,
    hue: GOLD,
    verb: "Divining the chosen foe",
    flavor: ["Naming the beast…", "Fixing the season's sigil…"],
  },
  find_encounter: {
    icon: GiMagnifyingGlass,
    hue: SCRY_BLUE,
    verb: "Hunting the encounter",
    flavor: ["Sifting the bestiary…", "Matching the boss by name…"],
  },
  get_spec_options: {
    icon: GiBattleGear,
    hue: ARCANE,
    verb: "Cataloguing the classes",
    flavor: ["Unrolling the roster…", "Listing specs and callings…"],
  },
  get_rankings_distribution: {
    icon: GiHistogram,
    hue: GOLD,
    verb: "Weighing the percentiles",
    flavor: ["Stacking the parses…", "Reading the brackets…", "Measuring the field…"],
  },
  compare_specs: {
    icon: GiCrossedSwords,
    hue: EMBER,
    verb: "Pitting spec against spec",
    flavor: ["Setting the scales…", "Contrasting the callings…"],
  },
  // --- Report deep-dive ---
  get_report_fights: {
    icon: GiScrollUnfurled,
    hue: GOLD,
    verb: "Unsealing the battle chronicles",
    flavor: ["Tallying the fallen…", "Reading the blood-ink ledgers…", "Counting every pull…"],
  },
  get_report_table: {
    icon: GiScrollQuill,
    hue: ARCANE,
    verb: "Tabulating the deeds",
    flavor: ["Summing each blow struck…", "Breaking down the abilities…", "Totting the ledger…"],
  },
  get_report_events: {
    icon: GiBleedingWound,
    hue: CRIMSON,
    verb: "Replaying the fray",
    flavor: ["Tracing the timeline…", "Reliving each heartbeat…"],
  },
  get_report_graph: {
    icon: GiChart,
    hue: SCRY_BLUE,
    verb: "Charting the tides of battle",
    flavor: ["Plotting the rise and fall…", "Drawing the arc of the fight…"],
  },
  get_report_rankings: {
    icon: GiPodium,
    hue: GOLD,
    verb: "Ranking the champions",
    flavor: ["Awarding the colours…", "Reading the podium…"],
  },
  get_report_player_details: {
    icon: GiPerson,
    hue: ARCANE,
    verb: "Inspecting the champion",
    flavor: ["Reading gear and talents…", "Studying the loadout…"],
  },
  get_report_master_data: {
    icon: GiStoneTablet,
    hue: GOLD,
    verb: "Deciphering the master runes",
    flavor: ["Naming actors and spells…", "Resolving the ancient ids…"],
  },
  // --- Individual characters ---
  get_character_zone_rankings: {
    icon: GiTrophy,
    hue: GOLD,
    verb: "Reading the hero's saga",
    flavor: ["Leafing the zone annals…", "Gathering past glories…"],
  },
  get_character_encounter_rankings: {
    icon: GiHealthPotion,
    hue: VERDANT,
    verb: "Recalling the hero's duels",
    flavor: ["Counting old victories…", "Reading parse history…"],
  },
  // --- Utility / escape hatch ---
  check_rate_limit: {
    icon: GiHourglass,
    hue: EMBER,
    verb: "Consulting the mana reserves",
    flavor: ["Gauging the arcane budget…", "Reading the sandglass…"],
  },
  run_wcl_graphql: {
    icon: GiMagicSwirl,
    hue: ARCANE,
    verb: "Weaving a raw incantation",
    flavor: ["Threading the leyline query…", "Shaping the spell by hand…"],
  },
  // --- Grounding ---
  web_search: {
    icon: GiCrystalBall,
    hue: SCRY_BLUE,
    verb: "Scrying the far realms",
    flavor: ["Peering through the mists…", "Whispers from distant lands…"],
  },
};

export const DEFAULT_SPELL: Spell = {
  icon: GiSpellBook,
  hue: "var(--glow)",
  verb: "Weaving a spell",
  flavor: ["The runes stir…", "Arcane energies gather…"],
};

export function spellFor(name: string): Spell {
  return SPELLS[name] ?? DEFAULT_SPELL;
}
