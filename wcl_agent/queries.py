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
