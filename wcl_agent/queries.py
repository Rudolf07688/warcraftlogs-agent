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


# Feature 013: recent reports for several characters in ONE request. Each character is an
# aliased field (c0, c1, …) inside a single characterData block; an unknown character
# resolves to null. Confirmed against the live API: the pagination field is `data`.
def recent_reports_query(n: int) -> str:
    decls = ", ".join(f"$n{i}: String!, $s{i}: String!, $r{i}: String!" for i in range(n))
    fields = "\n".join(
        f"    c{i}: character(name: $n{i}, serverSlug: $s{i}, serverRegion: $r{i}) {{\n"
        "      recentReports(limit: $limit) {\n"
        "        data { code title startTime endTime zone { id name } guild { name } }\n"
        "      }\n"
        "    }"
        for i in range(n)
    )
    return f"query RecentReports({decls}, $limit: Int!) {{\n  characterData {{\n{fields}\n  }}\n}}"


# Feature 013: boss pulls/kills/difficulty for several reports in ONE request (r0, r1, …).
def report_details_query(n: int) -> str:
    decls = ", ".join(f"$c{i}: String!" for i in range(n))
    fields = "\n".join(
        f"    r{i}: report(code: $c{i}) {{\n"
        "      endTime\n"
        "      zone { id }\n"
        "      fights(killType: Encounters) { encounterID kill difficulty }\n"
        "    }"
        for i in range(n)
    )
    return f"query ReportDetails({decls}) {{\n  reportData {{\n{fields}\n  }}\n}}"
