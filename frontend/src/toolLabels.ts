// Friendly, user-facing phrases for each agent tool, shown in the animated
// "thinking" indicator while that tool runs.
const TOOL_LABELS: Record<string, string> = {
  find_encounter: "Finding the encounter",
  get_selected_encounter: "Checking the encounter",
  get_spec_options: "Checking specs",
  get_rankings_distribution: "Pulling rankings",
  compare_specs: "Comparing specs",
  get_report_fights: "Loading the report",
  get_report_table: "Analyzing the fight",
  get_report_events: "Scanning combat events",
  get_report_graph: "Reading the timeline",
  get_report_rankings: "Checking parses",
  get_report_player_details: "Reading gear & talents",
  get_report_master_data: "Resolving names",
  get_character_zone_rankings: "Looking up the character",
  get_character_encounter_rankings: "Looking up the character",
  check_rate_limit: "Checking API budget",
  run_wcl_graphql: "Querying Warcraft Logs",
};

export const THINKING_DEFAULT = "Thinking";

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? "Searching Warcraft Logs";
}
