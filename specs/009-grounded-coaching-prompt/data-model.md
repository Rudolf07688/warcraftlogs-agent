# Data Model: Grounded, Evidence-Based Coaching

**Feature**: 009-grounded-coaching-prompt · **Date**: 2026-10-07

Typed per Constitution IV: **Pydantic** for data crossing a boundary (model output
parsed at the edge, REST bodies); **dataclasses** for in-process value objects (tool
computations, the guide-meta registry). Tool *return values* stay plain `dict`s because
ADK serialises them to the model — each is built from a dataclass via `asdict`, so the
shape has one typed source.

---

## 1. Persistent: `spec_guides` (extended)

Existing table (feature 008). Migration `0009_spec_guide_provenance` adds four nullable
columns; no backfill (pre-existing rows ⇒ unknown freshness, FR-027).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `game_patch` | `String(20)` | yes | Patch the guide targets, as stated by the generator (e.g. `"12.1"`). `NULL` ⇒ unknown. |
| `generated_at` | `DateTime(tz)` | yes | When the current markdown was successfully generated (unlike `updated_at`, not bumped by status flips). |
| `sources` | `JSON` | yes | `[{title, uri}]` from web-grounding records during generation; `[]` when no web search. |
| `major_cooldowns` | `JSON` | yes | `[GuideCooldown]` (below). `NULL` ⇒ no machine-readable cooldowns ⇒ rate-only coaching. |

**State transitions** (unchanged statuses `pending → ready | failed`): on `ready`, all
four columns are written together with `guide_markdown`; on `failed`, they are left
untouched; on `force` regeneration they are overwritten only on success.

**Derived (not stored)** `freshness`: `current | possibly_stale | unknown` =
`guide_freshness(game_patch, current_patch())` (research R8). Computed at read time so
it changes when a new patch partition appears, without a write.

## 2. Boundary model: `GuideMetaBlock` (Pydantic, backend)

Parsed from the fenced `guide-meta` JSON block at the end of the generator output.

```text
GuideMetaBlock
  patch: str | None                 # "12.1" / "12.1.5"; stripped; max 20 chars
  major_cooldowns: list[GuideCooldownIn] = []   # max 15 entries

GuideCooldownIn
  name: str                         # 1–80 chars, as shown in game / logs
  spell_id: int | None              # game spell id when known (> 0)
  cooldown_s: float                 # 1 ≤ cooldown_s ≤ 600
  charges: int = 1                  # 1 ≤ charges ≤ 5
  talent_modified: bool = False     # build commonly changes this cooldown
```

Validation failures ⇒ one repair turn on the same generation session asking for the
block only (research R10); if that also fails, the block is ignored (guide still
`ready`, metadata NULL).

## 3. In-process registry: `wcl_agent.guide_meta` (dataclasses)

```text
@dataclass(frozen=True) GuideCooldown
  name: str; spell_id: int | None; cooldown_s: float; charges: int; talent_modified: bool

@dataclass(frozen=True) GuideMeta
  class_name: str                   # WCL PascalCase, e.g. "Mage"
  spec: str                         # e.g. "Fire"
  game_patch: str | None
  generated_at: datetime | None
  cooldowns: tuple[GuideCooldown, ...]

set_guide_meta(meta: GuideMeta) -> None
get_guide_meta(class_name: str, spec: str) -> GuideMeta | None
```

Filled by the backend at startup (all `ready` rows) and after each successful
generation. Empty in the CLI. Keyed by `(class_name, spec)`.

## 4. Tool value objects (dataclasses → dict results)

### 4.1 `Provenance` / `Completeness` (shared by every WCL tool, research R11)

```text
Provenance
  report_code, fight_id, encounter_id, difficulty, partition, metric,
  source_id, compare, timeframe: optional (only set keys are emitted)
  fetched_at: str (ISO-8601 UTC)

Completeness
  has_more: bool = False            # more pages / nextPageTimestamp present
  truncated: bool = False           # result exceeded the size cap
  sample_size: int | None = None
  sample_scope: str | None = None   # "full" | "top_of_leaderboard" | "band_clipped"
```

### 4.2 `PercentileContext` (inside `get_report_rankings` players, FR-018)

```text
population: "rankings" | "parses"   # from compare
timeframe: "historical" | "today"
rank_percent: float | None          # overall
bracket_percent: float | None       # item-level bracket
bracket: int | None; item_level: float | None
partition: int | None; metric: str; encounter_id: int; difficulty: int
total_parses: int | None            # sample size N
```

### 4.3 `BenchmarkResult` (`compare_player_to_cohort`, US2)

```text
status: "success" | "limited" | "error"
player: {name, source_id, class, spec, amount, duration_s, item_level,
         dead_s: float, alive_s: float,
         rate_basis: "alive_time",       # player rates ÷ alive_s (FR-015a)
         percentile: PercentileContext}
cohort: {
  size: int, requested_size: int,
  members: [{name, amount, duration_s, item_level, report_code, fight_id, link}],
  criteria: {encounter_id, difficulty, spec, metric, partition, kill_only: true,
             duration_window_pct: 15 | 25, percentile_band: [75, 95],
             band_sampled: [lo, hi]},
  unmet_criteria: [str],            # e.g. "duration window widened to ±25%", "band clipped"
  label: "matched" | "anecdotal" | "directional"
}
measures: [{
  ability: {name, guid}, player_casts_per_min: float,
  cohort_median_per_min: float, cohort_min: float, cohort_max: float,
  cohort_users: int                 # members who cast it at least once
}]                                  # union of player's and cohort's top abilities, ≤ 20
throughput: {player_amount, cohort_median, cohort_min, cohort_max}
provenance, completeness
```

Rules: `label = "anecdotal"` when `size == 1`; `"directional"` when `2 ≤ size < 3` or
any criterion unmet; else `"matched"`. Wipes ⇒ `status: "limited"`, no cohort.
Player rates use `alive_s`; cohort members' rates use their fight duration (research
R3). `criteria.partition` is the partition of the player's pull (FR-014).

### 4.3a `AmbiguousPlayer` error (both new tools, FR-006)

```text
status: "error"
error_message: "Player name '<name>' matches N actors in this fight; pass source_id."
candidates: [{source_id, name, server, class, spec}]
```

Emitted when `player_name` matches more than one actor and no `source_id` was given.
`source_id` (when > 0) always wins over `player_name`.

### 4.3b Shared fight-time helpers (`wcl_agent/fight_time.py`)

```text
merge_intervals(intervals) -> list[(start, end)]
dead_windows(death_ts, next_cast_ts, fight_end) -> list[(start, end)]
fetch_dead_windows(report_code, fight_id, source_id, fight_end) -> list[(start, end)]
intermission_windows(fight_start, fight_end, phase_transitions, intermission_ids)
eligible_seconds(fight_start, fight_end, *window_lists) -> float
```

Created in US2 (time alive), reused by US4 (eligible time). **Eligible time ≠ WCL
`activeTime`**: the latter is time spent casting (a performance measure) and must not
be used as an opportunity window.

### 4.4 `CooldownUsage` (`get_cooldown_usage`, US4)

```text
status: "success" | "error"            # ambiguous name ⇒ §4.3a
player: {name, source_id, class, spec}
time: {fight_s, dead_s, intermission_s, eligible_s,
       excluded_windows_unknown: [str]}          # e.g. "target immunity outside intermissions"
guide: {available: bool, game_patch, freshness, generated_at} | null
cooldowns: [{                                    # only when guide.available
  name, spell_id, cooldown_s, charges, talent_modified,
  uses: int, opportunities: int, approximate: true,
  freshness_caveat: bool                         # guide possibly_stale | unknown
}]
rates: [{ability: {name, guid}, casts: int, casts_per_min: float}]   # all abilities
provenance, completeness
```

Rules: `opportunities = 1 + floor(eligible_s / cooldown_s) + (charges − 1)`;
`uses` matched by `spell_id == guid`, else case-insensitive name; a guide cooldown
with no matching cast ⇒ `uses = 0`.

## 5. REST additions (guides, US5)

`GuideListItem` and `GuideOut` gain: `game_patch: str | None`, `generated_at:
datetime | None`, `freshness: "current" | "possibly_stale" | "unknown" | None`
(`None` when status ≠ ready). See `contracts/rest-guides.md`.

## 6. Prompt-side entities (no storage)

Evidence kinds (observed / benchmarked / guidance / inferred / unknown) and per-fix
confidence (high / medium / low) are instructions to the model (contracts/prompt.md),
not stored data. An analysis trace is out of scope.
