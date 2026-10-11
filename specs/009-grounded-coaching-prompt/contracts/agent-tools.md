# Contract: Agent tools (Warcraft Logs layer)

All tools are plain sync functions in `wcl_agent/`, registered once in
`wcl_agent/agent.py::TOOLS` (single source of truth). Every result is a `dict` with a
`status` key. **Changes to existing tools are additive only** — backend consumers
(`services/encounters.py`, `tool_summary.py`, `raids.py`, known-entity capture) read
existing keys by tool name and must keep working unchanged.

---

## 1. Shared envelope (all WCL tools) — FR-020, FR-022

Every successful WCL tool result gains:

```jsonc
"provenance": {            // only keys that apply to this call
  "report_code": "cFHpyKdLWAajwZCM", "fight_id": 9,
  "encounter_id": 3470, "difficulty": 4, "partition": 1,
  "metric": "dps", "source_id": 7,
  "compare": "Rankings", "timeframe": "Historical",
  "fetched_at": "2026-10-07T14:03:11Z"
},
"completeness": {
  "has_more": false,       // more pages / nextPageTimestamp present
  "truncated": false,      // payload exceeded the size cap (preview only)
  "sample_size": null,
  "sample_scope": null     // "full" | "top_of_leaderboard" | "band_clipped"
}
```

Built by one helper (`wcl_agent/provenance.py`). `_cap` output is unchanged; the
helper sets `completeness.truncated = True` when `_cap` truncated.

Tool-specific mappings:

| Tool | `has_more` | `sample_size` / `sample_scope` |
|---|---|---|
| `get_rankings_distribution`, `compare_specs` | `more_pages_available` | fetched N / `top_of_leaderboard` if more pages else `full` |
| `get_report_events` | `nextPageTimestamp != null` | — |
| `get_report_table` / `graph` / `rankings` / `player_details` / `master_data` / `fights` | false | — |
| `get_character_*_rankings` | false | — |
| `run_wcl_graphql` | false | — (provenance `{fetched_at}` only) |

## 2. Changed: `get_report_rankings` — FR-018, FR-019

```python
def get_report_rankings(
    report_code: str,
    fight_id: int = 0,
    compare: str = "Rankings",      # "Rankings" (best per character) | "Parses" (all pulls, ~2 weeks)
    timeframe: str = "Historical",  # "Historical" (at time of kill) | "Today"
) -> dict
```

- Validates `compare`/`timeframe` against whitelists; error otherwise.
- Existing `rankings` key unchanged. Adds `percentiles`: one `PercentileContext`
  (data-model §4.2) per ranked player per fight, flattened from the raw JSON, so the
  model never has to dig through nested roles.

## 3. Fixed: data-type whitelists

`TABLE_DATA_TYPES` / `EVENT_DATA_TYPES` match the probed API enums (research R5/R14):
`Resurrections` removed from both; `Summons` added to tables.

## 4. New: `compare_player_to_cohort` — US2, FR-014..FR-017

```python
def compare_player_to_cohort(
    report_code: str,
    fight_id: int,
    player_name: str,
    metric: str = "dps",            # dps | hps | bossdps (validated against METRICS)
    size: int = 5,                  # clamped to 1..5
    source_id: int = 0,             # disambiguates duplicate names; wins over player_name
) -> dict                           # BenchmarkResult, data-model §4.3
```

**Player resolution (shared with §5, FR-006)**: `masterData { actors(type: "Player")
{ id name server subType } }` (report-scoped, cached). `source_id > 0` → that actor;
else exact name match among actors present in the fight (`fights.friendlyPlayers`).
0 matches → `error` listing names present; >1 → `AmbiguousPlayer` error
(data-model §4.3a). The resolved `(name, server)` selects the `report.rankings` row
(rankings rows carry a character id, not the source id); the resolved `source_id`
selects the Casts-table entry (`entry.id`).

Docstring (model-facing) must state: *use for "how do I compare / why is my parse
low"; returns a matched cohort of strong-but-not-extreme kill parses with medians and
ranges; do NOT use get_rankings_distribution's top_parses as a benchmark.*

Algorithm (research R1–R4):
1. `report.rankings(fightIDs:[fight_id], playerMetric)` → player row (class, spec,
   amount, bracketData, totalParses N, rank/bracket percent), fight `kill`,
   `duration`, `encounter`, `difficulty`, `partition`. Player not found → `error`
   naming the players present. Fight not a kill → `status: "limited"`.
2. Band ranks `ceil(0.05N)..floor(0.25N)`; centre page `ceil(0.15N/100)`; fetch ≤3
   pages (`characterRankings`, same class/spec/metric/difficulty/partition). Page > 20
   ⇒ pages 18–20, `unmet_criteria += "band clipped"`, `sample_scope = band_clipped`.
3. Local filter: duration within ±15% of the player's; exclude the player's own
   character; nearest `size` by |Δduration|. Fewer than 3 ⇒ widen to ±25% and record.
4. Budget check (`rateLimitData`): remaining < 100 ⇒ size ≤ 3; < 40 ⇒ size 1.
5. `Casts` table per member fight (entry chosen by name) + the player's fight (entry
   chosen by resolved `source_id`) → casts per ability. Member rates ÷ member fight
   duration. **Player rates ÷ time alive** (FR-015a): `fetch_dead_windows` from
   `wcl_agent/fight_time.py` (Deaths table + one next-cast event per death);
   `player.dead_s`, `player.alive_s`, `rate_basis = "alive_time"`. Aggregate
   median/min/max; `cohort_users`.
6. Emit `members[].link` as `https://www.warcraftlogs.com/reports/<code>#fight=<id>`
   (built only from returned identifiers).

## 5. New: `get_cooldown_usage` — US4, FR-023..FR-025a

```python
def get_cooldown_usage(
    report_code: str,
    fight_id: int,
    player_name: str,
    source_id: int = 0,             # disambiguates duplicate names; wins over player_name
) -> dict                           # CooldownUsage, data-model §4.4
```

Player resolution and the ambiguous-name error are identical to §4 (one shared
helper, `resolve_player`, in `wcl_agent/fight_time.py`).

Docstring must state: *use before saying a cooldown was under-used; express results
as "N of ~M opportunities" only when `guide.available`; otherwise compare rates and
never say "missed".*

Algorithm (research R5–R7):
1. `report { phases; fights(fightIDs){startTime endTime kill phaseTransitions} }`.
2. `resolve_player` (§4) → `source_id`; `Casts` table filtered to the fight → the
   entry with `id == source_id` (class/spec from `icon`, e.g. `Mage-Fire`;
   per-ability totals).
3. `fetch_dead_windows` (shared, `wcl_agent/fight_time.py`): `Deaths` table → the
   player's death timestamps; for each, first subsequent player cast event
   (`events(Casts, sourceID, startTime, limit 1)`) closes the dead window.
4. `intermission_windows` from `phaseTransitions` × `phases.isIntermission`.
5. `eligible_s = fight_s − merged(dead ∪ intermission)` (**not** WCL `activeTime`).
6. `get_guide_meta(class, spec)` → cooldowns; `freshness = guide_freshness(patch,
   current_patch())`; compute uses/opportunities; `freshness_caveat` when not current.

## 6. New helpers (not tools)

- `wcl_agent/fight_time.py` (created in US2, reused in US4): `resolve_player`,
  `merge_intervals`, `dead_windows`, `fetch_dead_windows`, `intermission_windows`,
  `eligible_seconds` (data-model §4.3b).
- `wcl_agent/guide_meta.py`: `GuideCooldown`, `GuideMeta`, `set_guide_meta`,
  `get_guide_meta` (data-model §3).
- `wcl_agent/patch.py`: `current_patch() -> str | None` (cached `MENU_DISCOVERY`;
  newest non-frozen zone with Heroic difficulty → default partition name) and
  `guide_freshness(guide_patch, current) -> Literal["current","possibly_stale","unknown"]`.

## 7. Unchanged

`get_selected_encounter`, `find_encounter`, `get_spec_options`, `get_report_fights`
(beyond envelope), `get_report_table`, `get_report_events`, `get_report_graph`,
`get_report_player_details`, `get_report_master_data`, `get_character_*`,
`create_chart`, `check_rate_limit`, `run_wcl_graphql`, `web_search` sub-agent.
