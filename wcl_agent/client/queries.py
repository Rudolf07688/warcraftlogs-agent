"""GraphQL query strings for the Warcraft Logs v2 API."""

# One call builds the whole selection tree for the menu. `characterRankings`
# returns a JSON scalar, so zones/encounters/difficulties/partitions are the
# only structured data we need up front.
MENU_DISCOVERY = """
query MenuDiscovery {
  worldData {
    zones {
      id
      name
      frozen
      expansion { id name }
      difficulties { id name }
      partitions { id name default }
      encounters { id name }
    }
  }
}
""".strip()


# Feature 015: the live class/spec list (slugs are the className/specName filter values).
GAME_CLASSES = """
query GameClasses {
  gameData {
    classes { id name slug specs { id name slug } }
  }
}
""".strip()


# Feature 015 (research R5): top logs-only rankings for one spec on one encounter, with each
# entry's talents and gear. ``leaderboard: LogsOnly`` keeps out Blizzard leaderboard rows
# that have no report, talents or gear.
SPEC_RANKINGS = """
query SpecRankings(
  $encounterID: Int!
  $className: String!
  $specName: String!
  $metric: CharacterRankingMetricType!
  $difficulty: Int
  $partition: Int
  $page: Int
) {
  worldData {
    encounter(id: $encounterID) {
      characterRankings(
        className: $className
        specName: $specName
        metric: $metric
        difficulty: $difficulty
        partition: $partition
        leaderboard: LogsOnly
        includeCombatantInfo: true
        page: $page
      )
    }
  }
}
""".strip()


# Rankings for one boss, optionally filtered by class/spec. `characterRankings`
# is a JSON scalar and takes no sub-selection.
ENCOUNTER_RANKINGS = """
query EncounterRankings(
  $encounterID: Int!
  $difficulty: Int!
  $metric: CharacterRankingMetricType!
  $className: String
  $specName: String
  $page: Int!
  $partition: Int
) {
  worldData {
    encounter(id: $encounterID) {
      id
      name
      characterRankings(
        difficulty: $difficulty
        metric: $metric
        className: $className
        specName: $specName
        page: $page
        partition: $partition
        includeCombatantInfo: false
      )
    }
  }
}
""".strip()


# Feature 014: the field selections below are shared by the single queries and their aliased
# batch forms (c0, c1, … / r0, r1, …), which the recent-raids refresh uses so one request
# covers every character or up to 10 reports (PERF-001, 2026-10-18).

# char_id: a character's WCL identity from name/realm/region. Everything else about the
# character is then queried by id, so cached entries can be keyed by it.
CHARACTER_REF_FIELDS = "id name classID server { slug region { slug } }"

CHARACTER_REF = (
    "query CharRef($name: String!, $server: String!, $region: String!) {\n"
    "  characterData {\n"
    "    character(name: $name, serverSlug: $server, serverRegion: $region) {\n"
    f"      {CHARACTER_REF_FIELDS}\n"
    "    }\n"
    "  }\n"
    "}"
)


def character_refs_query(n: int) -> str:
    """``CHARACTER_REF`` for n characters in one request (variables n{i}, s{i}, r{i})."""
    decls = ", ".join(f"$n{i}: String!, $s{i}: String!, $r{i}: String!" for i in range(n))
    fields = "\n".join(
        f"    c{i}: character(name: $n{i}, serverSlug: $s{i}, serverRegion: $r{i}) {{ {CHARACTER_REF_FIELDS} }}"
        for i in range(n)
    )
    return f"query ResolveCharacters({decls}) {{\n  characterData {{\n{fields}\n  }}\n}}"


# char_reports: a character's most recent reports, by WCL character id.
RECENT_REPORTS_FIELDS = (
    "recentReports(limit: $limit) { data { code title startTime endTime zone { id name } guild { name } } }"
)


def character_reports_query(n: int) -> str:
    """Recent reports of n characters by id in one request (variables id{i}, limit)."""
    decls = ", ".join(f"$id{i}: Int!" for i in range(n))
    fields = "\n".join(f"    c{i}: character(id: $id{i}) {{ {RECENT_REPORTS_FIELDS} }}" for i in range(n))
    return f"query RecentReportsByIds({decls}, $limit: Int!) {{\n  characterData {{\n{fields}\n  }}\n}}"


# report_summary: fights, bosses, kills/wipes and roster of one report — the single source
# for get_report_fights, get_report_metadata and the recent-raids details.
REPORT_SUMMARY_FIELDS = (
    "title startTime endTime zone { id name } guild { name } "
    'masterData { actors(type: "Player") { id name subType } } '
    "fights { id name encounterID difficulty kill averageItemLevel size friendlyPlayers "
    "startTime keystoneLevel keystoneBonus keystoneTime }"
)

REPORT_SUMMARY = (
    "query ReportSummary($code: String!) {\n"
    f"  reportData {{ report(code: $code) {{ {REPORT_SUMMARY_FIELDS} }} }}\n"
    "}"
)


def report_summaries_query(n: int) -> str:
    """``REPORT_SUMMARY`` for n reports in one request (variables c{i})."""
    decls = ", ".join(f"$c{i}: String!" for i in range(n))
    fields = "\n".join(f"    r{i}: report(code: $c{i}) {{ {REPORT_SUMMARY_FIELDS} }}" for i in range(n))
    return f"query ReportsBatch({decls}) {{\n  reportData {{\n{fields}\n  }}\n}}"
